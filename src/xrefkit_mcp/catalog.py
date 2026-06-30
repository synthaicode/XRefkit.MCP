from __future__ import annotations

import base64
import io
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .contracts import builtin_tool_contracts
from .repository import (
    first_heading,
    first_paragraph,
    first_xid,
    git_last_modified,
    markdown_xid_link_targets,
    markdown_xid_only_text,
    markdown_xid_links,
    parse_meta_bullets,
    read_text,
    relative_to_repo,
    repository_fingerprint,
    scalar_list,
    stable_hash,
)
from .schemas import (
    ClientObligation,
    ClientToolDistribution,
    ClientToolFile,
    ClientToolManifestEntry,
    ClientToolPipPackage,
    ClosureContract,
    KnowledgeCatalogEntry,
    SkillCatalogEntry,
    SkillRankResult,
    RuntimeRoleContract,
    StartupContext,
    StartupReference,
    ToolContract,
    WorkflowCatalogEntry,
    XRefDocument,
)
from .startup_contract_pack import (
    normalized_startup_contract_pack_body,
    startup_contract_pack_hash,
)


TOKEN_RE = re.compile(r"[A-Za-z0-9_+#.-]+")
IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([A-Za-z0-9_.]+)", re.MULTILINE)
CLIENT_TOOL_PACKAGE_ID = "xrefkit-client-python-tools"
CLIENT_TOOL_PACKAGE_VERSION = "0.1.0"
CACHE_MAX_VERSION_PAYLOAD_RATIO = 0.5
STARTUP_REFERENCE_DEFINITIONS = [
    (
        "0B5C58B5E5B2",
        "base_control",
    ),
    (
        "5A1C8E4D2F90",
        "base_control",
    ),
    (
        "6C0B62D6366A",
        "xref_routing",
    ),
    (
        "8A666C1FD121",
        "base_control",
    ),
    (
        "A7F3C92D4E11",
        "base_control",
    ),
    (
        "4A423E72D2ED",
        "base_control",
    ),
]
STOP_TOKENS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "by",
    "code",
    "for",
    "in",
    "is",
    "of",
    "or",
    "review",
    "skill",
    "the",
    "to",
    "user",
    "with",
}


@dataclass(frozen=True)
class XRefCatalog:
    repo_root: Path
    repository_fingerprint: str
    catalog_version: str
    knowledge: list[KnowledgeCatalogEntry]
    skills: list[SkillCatalogEntry]
    tools: list[ToolContract]

    @classmethod
    def build(cls, repo_root: str | Path) -> "XRefCatalog":
        root = Path(repo_root).resolve()
        if not root.exists():
            raise FileNotFoundError(root)
        knowledge = _build_knowledge(root)
        skills = _build_skills(root)
        tools = builtin_tool_contracts()
        version_basis = "\n".join(
            [entry.content_hash for entry in knowledge]
            + [entry.skill_id + entry.summary for entry in skills]
            + [tool.tool_id + tool.version for tool in tools]
        )
        catalog_version = stable_hash(version_basis)[:16]
        return cls(
            repo_root=root,
            repository_fingerprint=repository_fingerprint(root),
            catalog_version=catalog_version,
            knowledge=knowledge,
            skills=skills,
            tools=tools,
        )

    def get_repository_identity(self) -> dict[str, str]:
        return {
            "repository_fingerprint": self.repository_fingerprint,
            "fingerprint_algorithm": "sha256",
            "fingerprint_basis": "resolved_repository_root",
            "cache_namespace": self.repository_fingerprint,
        }

    def list_knowledge_catalog(self, limit: int | None = None) -> list[dict]:
        return [entry.to_dict() for entry in self.knowledge[: limit or None]]

    def search_knowledge_catalog(self, query: str, limit: int = 10) -> list[dict]:
        return [entry.to_dict() for entry in _rank_entries(query, self.knowledge)[:limit]]

    def expand_knowledge(self, xid: str) -> dict:
        entry = self._knowledge_by_xid(xid)
        content = read_text(self.repo_root / entry.path)
        return {"entry": entry.to_dict(), "content": content}

    def build_knowledge_context(self, query: str, limit: int = 5) -> dict:
        ranked = _rank_entries(query, self.knowledge)[:limit]
        by_xid = {entry.xid: entry for entry in self.knowledge}
        expanded: list[dict] = []
        missing: list[dict] = []
        seen: set[str] = set()
        for entry in ranked:
            for candidate_xid in [entry.xid, *entry.requires_knowledge]:
                if candidate_xid in seen:
                    continue
                seen.add(candidate_xid)
                candidate = by_xid.get(candidate_xid)
                if not candidate:
                    missing.append(
                        {
                            "xid": candidate_xid,
                            "reason": "referenced knowledge was not found in the catalog",
                        }
                    )
                    continue
                expanded.append(self.expand_knowledge(candidate.xid))
        return {"entries": expanded, "missing": missing}

    def list_skills(
        self,
        limit: int | None = None,
        include_content: bool = True,
    ) -> list[dict]:
        fresh_entries = [
            _fresh_skill_entry(entry, self.repo_root)
            for entry in self.skills[: limit or None]
        ]
        results = [entry.to_dict() for entry in fresh_entries]
        if not include_content:
            for entry, result in zip(fresh_entries, results, strict=True):
                result["meta_content"] = None
                result["skill_content"] = None
                result["document_versions"] = _skill_document_versions(
                    entry,
                    self.repo_root,
                    self.repository_fingerprint,
                )
        return results

    def get_skill(
        self,
        skill_id: str,
        known_document_versions: dict[str, str] | None = None,
    ) -> dict:
        entry = self._skill_by_id(skill_id)
        entry = _fresh_skill_entry(entry, self.repo_root)
        result = entry.to_dict()
        result["client_tool_download"] = _client_tool_download_policy(entry)
        if known_document_versions is None:
            return result

        documents: list[dict] = []
        for relative_path in [entry.meta_path, entry.path]:
            path = self.repo_root / relative_path
            text = read_text(path)
            document = _xref_document(path, self.repo_root, text)
            documents.append(
                _conditional_document_response(
                    document,
                    known_document_versions.get(document.xid),
                    self.repository_fingerprint,
                )
            )
        result["meta_content"] = None
        result["skill_content"] = None
        result["documents"] = documents
        return result

    def get_skill_requirements(self, skill_id: str) -> dict:
        entry = self._skill_by_id(skill_id)
        return {
            "skill_id": entry.skill_id,
            "required_knowledge": entry.required_knowledge,
            "required_tools": entry.required_tools,
            "client_tool_download": _client_tool_download_policy(entry),
            "closure_contract": entry.closure_contract.to_dict(),
            "meta_path": entry.meta_path,
            "meta_content": entry.meta_content,
            "meta_links": entry.meta_links,
            "skill_doc": entry.path,
            "skill_content": entry.skill_content,
            "skill_links": entry.skill_links,
            "missing": entry.missing,
        }

    def rank_skills_for_purpose(self, purpose: str, limit: int = 5) -> list[dict]:
        query_tokens = _tokens(purpose)
        results: list[SkillRankResult] = []
        available_tools = {tool.tool_id: tool.version for tool in self.tools}
        for skill in self.skills:
            facets: list[str] = []
            score = 0.0
            for label, values, weight in [
                ("skill_id", [skill.skill_id], 0.15),
                ("intent", skill.intent, 0.25),
                ("target", skill.target_artifacts, 0.25),
                ("applies_when", skill.applies_when, 0.2),
                ("summary", [skill.summary], 0.2),
                ("inputs", skill.inputs, 0.1),
            ]:
                matched = _matched_values(query_tokens, values)
                if matched:
                    facets.extend(f"{label}={value}" for value in matched[:3])
                    score += weight
                    score += min(0.1, 0.02 * _overlap_count(query_tokens, matched))
            blocked = _matched_values(query_tokens, skill.not_for, use_stop_words=True)
            if blocked:
                facets.extend(f"not_for={value}" for value in blocked[:3])
                score *= 0.25
            if "roslyn" in query_tokens and "roslyn" in _tokens(
                " ".join([skill.skill_id, skill.summary, *skill.applies_when])
            ):
                score += 0.15
            missing_tools = [
                item.get("tool_id", "")
                for item in skill.required_tools
                if item.get("tool_id") and item.get("tool_id") not in available_tools
            ]
            readiness = {"runnable": not missing_tools, "missing_tool_contracts": missing_tools}
            results.append(
                SkillRankResult(
                    skill_id=skill.skill_id,
                    matched_facets=facets,
                    closure_preview=skill.closure_contract,
                    required_knowledge=skill.required_knowledge,
                    execution_readiness=readiness,
                    score=round(score, 4),
                )
            )
        results.sort(key=lambda item: item.score, reverse=True)
        return [item.to_dict() for item in results[:limit]]

    def list_tool_contracts(self) -> list[dict]:
        return [contract.to_dict() for contract in self.tools]

    def list_workflows(self) -> list[dict]:
        return [workflow.to_dict() for workflow in _build_workflows(self.repo_root)]

    def get_client_tool_manifest(self) -> dict:
        return _client_tool_distribution(self.repo_root).to_dict()

    def get_client_tool_file(self, path: str) -> dict:
        normalized = path.replace("\\", "/")
        for tool_file in _client_tool_files(self.repo_root):
            if tool_file.path == normalized:
                return tool_file.to_dict()
        raise KeyError(f"client tool file not found: {path}")

    def get_client_tool_bundle(self) -> dict:
        return {
            "distribution": _client_tool_distribution(self.repo_root).to_dict(),
            "files": [file.to_dict() for file in _client_tool_files(self.repo_root)],
        }

    def get_client_tool_pip_package(self) -> dict:
        return _client_tool_pip_package(self.repo_root).to_dict()

    def check_client_tool_versions(self, installed: dict[str, str] | None = None) -> dict:
        installed = installed or {}
        expected = {
            CLIENT_TOOL_PACKAGE_ID: CLIENT_TOOL_PACKAGE_VERSION,
            "xrefkit-client-tools": CLIENT_TOOL_PACKAGE_VERSION,
        }
        results: list[dict[str, str | bool]] = []
        overall_ok = True
        for package_id, version in expected.items():
            actual = installed.get(package_id)
            ok = actual == version
            if not ok:
                overall_ok = False
            status = "ok" if ok else "missing" if actual is None else "mismatch"
            results.append(
                {
                    "package_id": package_id,
                    "expected_version": version,
                    "installed_version": actual or "",
                    "status": status,
                    "ok": ok,
                }
            )
        return {
            "ok": overall_ok,
            "expected": expected,
            "results": results,
            "instructions": [
                "Client should call this after selecting a Skill that declares client-side required_tools.",
                "If ok is false, install the package returned by get_client_tool_pip_package before executing that Skill's client-side tools.",
            ],
        }

    def get_document_by_xid(
        self,
        xid: str,
        known_version: str | None = None,
    ) -> dict:
        for path in _managed_markdown_files(self.repo_root):
            text = read_text(path)
            if first_xid(text) == xid:
                return _conditional_document_response(
                    _xref_document(path, self.repo_root, text),
                    known_version,
                    self.repository_fingerprint,
                )
        raise KeyError(f"document xid not found: {xid}")

    def get_startup_context(
        self,
        known_document_versions: dict[str, str] | None = None,
    ) -> dict:
        known_document_versions = known_document_versions or {}
        references: list[StartupReference] = []
        missing: list[dict[str, str]] = []
        managed_documents = _managed_markdown_by_xid(self.repo_root)
        for expected_xid, layer in STARTUP_REFERENCE_DEFINITIONS:
            resolved = managed_documents.get(expected_xid)
            if resolved is None:
                missing.append(
                    {
                        "xid": expected_xid,
                        "reason": "startup reference XID not found",
                    }
                )
                continue
            path, text = resolved
            rel_path = relative_to_repo(path, self.repo_root)
            document = _xref_document(path, self.repo_root, text)
            known_version = known_document_versions.get(expected_xid)
            not_modified = known_version == document.content_hash
            cache_status = (
                "not_modified"
                if not_modified
                else "modified"
                if known_version
                else "bypassed"
            )
            references.append(
                StartupReference(
                    xid=expected_xid,
                    title=first_heading(text, Path(rel_path).stem),
                    layer=layer,  # type: ignore[arg-type]
                    required_at_init=True,
                    summary=first_paragraph(text),
                    content=None,
                    links=markdown_xid_link_targets(text),
                    content_hash=document.content_hash,
                    cache_status=cache_status,
                    content_omitted=True,
                    included_in_startup_contract_pack=True,
                    cache_policy={"cache_recommended": False, "reason": "startup body represented by startup_contract_pack"},
                    repository_fingerprint=self.repository_fingerprint,
                )
            )
        return StartupContext(
            catalog_version=self.catalog_version,
            repository_identity=self.get_repository_identity(),
            access_policy={
                "mode": "mcp_only",
                "source_of_truth": "xrefkit_mcp",
                "applies_to": [
                    "startup references",
                    "XID-linked Markdown documents",
                    "Skill meta and procedure content",
                    "workflow definitions",
                    "knowledge catalog entries",
                    "tool contracts",
                    "closure contracts",
                    "unknown protocol",
                ],
                "forbidden_client_shortcuts": [
                    "Do not read XRefKit governance Markdown directly from the client filesystem when this MCP server is configured.",
                    "Do not resolve transferred Markdown links by filesystem path.",
                    "Do not open local Skill files to bypass get_skill.",
                    "Do not treat a local checkout as authoritative unless the user explicitly disables MCP-only mode.",
                ],
                "required_tools": {
                    "cache_identity": "get_repository_identity",
                    "startup": "get_startup_context",
                    "xid_link_resolution": "get_document_by_xid",
                    "skill_content": "get_skill",
                    "workflow_catalog": "list_workflows",
                },
            },
            context_injection_policy=_context_injection_policy(),
            session_context_deduplication=_session_context_deduplication(),
            client_instructions=[
                "A client may call get_repository_identity as a content-free cache namespace preflight; get_startup_context remains the first governance-content load.",
                "Materialize and apply startup references in load_order before routing task-specific work. Applying a reference means enforcing its operational contract in the client runtime; it does not require injecting the full document body into the model prompt unless context_injection_policy requires it.",
                "MCP-only mode is active: treat this MCP response as the source of truth for XRefKit governance content.",
                "Do not read XRefKit governance Markdown from the client filesystem while MCP-only mode is active.",
                "Do not assume referenced Markdown files exist on the client filesystem.",
                "When transferred Markdown content includes links entries, resolve a needed link by calling get_document_by_xid with the link xid.",
                "Use the returned document content as the authoritative text for that XID.",
                "For Skill entries, use skill_content as the procedure body and resolve skill_links through get_document_by_xid when needed.",
                "Keep client-side XID document cache entries only when cache_policy.cache_recommended is true.",
                "Fetch client-side tool manifests or packages only after a selected Skill declares client-side required_tools.",
                "Send cached content_hash values as known_version or known_document_versions; when cache_status is not_modified, use the locally hash-validated body instead of downloading it again.",
            ],
            client_obligations=_client_obligations(),
            link_resolution={
                "link_field": "links",
                "xid_field": "xid",
                "resolver_tool": "get_document_by_xid",
                "resolver_argument": "xid",
                "version_field": "content_hash",
                "conditional_argument": "known_version",
                "example_call": "get_document_by_xid({\"xid\": \"8A666C1FD121\"})",
            },
            load_order=[reference.xid for reference in references],
            startup_contract_pack=_startup_contract_pack(references),
            references=references,
            semantic_routing_references=_semantic_routing_references(),
            missing=missing,
        ).to_dict()

    def _knowledge_by_xid(self, xid: str) -> KnowledgeCatalogEntry:
        for entry in self.knowledge:
            if entry.xid == xid:
                return entry
        raise KeyError(f"knowledge xid not found: {xid}")

    def _skill_by_id(self, skill_id: str) -> SkillCatalogEntry:
        for entry in self.skills:
            if entry.skill_id == skill_id:
                return entry
        raise KeyError(f"skill not found: {skill_id}")


def _build_knowledge(root: Path) -> list[KnowledgeCatalogEntry]:
    entries: list[KnowledgeCatalogEntry] = []
    for path in sorted((root / "knowledge").glob("**/*.md")):
        text = read_text(path)
        xid = first_xid(text)
        missing: list[str] = []
        if not xid:
            xid = f"path:{relative_to_repo(path, root)}"
            missing.append("xid")
        rel = relative_to_repo(path, root)
        parts = Path(rel).parts
        domain = parts[1] if len(parts) > 2 else "knowledge"
        links = markdown_xid_links(text)
        entries.append(
            KnowledgeCatalogEntry(
                xid=xid,
                version=1,
                content_hash=stable_hash(text),
                revised_at=git_last_modified(root, path),
                title=first_heading(text, path.stem),
                domain=domain,
                summary=first_paragraph(text),
                applies_when=[],
                requires_knowledge=links,
                related_skills=[],
                related_capabilities=[],
                path=rel,
                missing=missing,
            )
        )
    return entries


def _managed_markdown_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirname in ["agent", "docs", "knowledge", "capabilities", "skills"]:
        base = root / dirname
        if base.exists():
            files.extend(sorted(base.glob("**/*.md")))
    return files


def _managed_markdown_by_xid(root: Path) -> dict[str, tuple[Path, str]]:
    documents: dict[str, tuple[Path, str]] = {}
    for path in _managed_markdown_files(root):
        text = read_text(path)
        xid = first_xid(text)
        if xid:
            documents.setdefault(xid, (path, text))
    return documents


def _xref_document(path: Path, root: Path, text: str) -> XRefDocument:
    xid = first_xid(text)
    if not xid:
        xid = f"path:{relative_to_repo(path, root)}"
    content = markdown_xid_only_text(text)
    return XRefDocument(
        xid=xid,
        title=first_heading(text, path.stem),
        path=relative_to_repo(path, root),
        summary=first_paragraph(text),
        content=content,
        links=markdown_xid_link_targets(text),
        content_hash=stable_hash(content),
    )


def _conditional_document_response(
    document: XRefDocument,
    known_version: str | None,
    repository_fingerprint: str,
) -> dict:
    cache_policy = _document_cache_policy(document, repository_fingerprint)
    if (
        known_version == document.content_hash
        and cache_policy["cache_recommended"]
    ):
        return {
            "xid": document.xid,
            "title": document.title,
            "content_hash": document.content_hash,
            "repository_fingerprint": repository_fingerprint,
            "cache_status": "not_modified",
            "content_omitted": True,
        }

    result = document.to_dict()
    result.update(
        {
            "repository_fingerprint": repository_fingerprint,
            "cache_status": (
                "bypassed"
                if known_version == document.content_hash
                else "modified"
                if known_version
                else "miss"
            ),
            "content_omitted": False,
            "cache_policy": cache_policy,
        }
    )
    return result


def _document_cache_policy(
    document: XRefDocument,
    repository_fingerprint: str,
) -> dict:
    full_document = document.to_dict()
    full_document["repository_fingerprint"] = repository_fingerprint
    version_request = {
        "xid": document.xid,
        "known_version": document.content_hash,
    }
    not_modified_response = {
        "xid": document.xid,
        "title": document.title,
        "content_hash": document.content_hash,
        "repository_fingerprint": repository_fingerprint,
        "cache_status": "not_modified",
        "content_omitted": True,
    }
    version_payload_bytes = _json_size(version_request) + _json_size(
        not_modified_response
    )
    document_payload_bytes = _json_size(full_document)
    ratio = (
        version_payload_bytes / document_payload_bytes
        if document_payload_bytes
        else 1.0
    )
    return {
        "cache_recommended": (
            not document.xid.startswith("path:")
            and ratio < CACHE_MAX_VERSION_PAYLOAD_RATIO
        ),
        "version_payload_bytes": version_payload_bytes,
        "document_payload_bytes": document_payload_bytes,
        "version_to_document_ratio": round(ratio, 6),
        "maximum_ratio": CACHE_MAX_VERSION_PAYLOAD_RATIO,
        "measurement_scope": "application_json_without_mcp_envelope",
    }


def _json_size(value: object) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def _skill_document_versions(
    entry: SkillCatalogEntry,
    root: Path,
    repository_fingerprint: str,
) -> list[dict]:
    versions: list[dict] = []
    for relative_path, text in [
        (entry.meta_path, entry.meta_content),
        (entry.path, entry.skill_content),
    ]:
        document = _xref_document(root / relative_path, root, text)
        versions.append(
            {
                "xid": document.xid,
                "path": document.path,
                "content_hash": document.content_hash,
                "repository_fingerprint": repository_fingerprint,
                "cache_policy": _document_cache_policy(
                    document,
                    repository_fingerprint,
                ),
            }
        )
    return versions


def _startup_contract_pack(references: list[StartupReference]) -> dict[str, object]:
    source_xids = [reference.xid for reference in references]
    expected_xids = [xid for xid, _layer in STARTUP_REFERENCE_DEFINITIONS]
    if source_xids != expected_xids:
        missing = [xid for xid in expected_xids if xid not in source_xids]
        extra = [xid for xid in source_xids if xid not in expected_xids]
        raise ValueError(
            "startup contract pack source XIDs do not match required startup order: "
            f"missing={missing}, extra={extra}"
        )
    source_hashes: dict[str, str] = {}
    for reference in references:
        if not reference.content_hash:
            raise ValueError(f"startup reference missing content_hash: {reference.xid}")
        source_hashes[reference.xid] = reference.content_hash
    return {
        "mode": "required_startup_contract_pack",
        "pack_version": 1,
        "source_xids": source_xids,
        "source_hashes": source_hashes,
        "pack_hash": startup_contract_pack_hash(),
        "body": normalized_startup_contract_pack_body(),
    }


def _fresh_skill_entry(entry: SkillCatalogEntry, root: Path) -> SkillCatalogEntry:
    meta_path = root / entry.meta_path
    if not meta_path.exists():
        return entry
    return _build_skill_entry(root, meta_path)


def _build_skill_entry(root: Path, meta_path: Path) -> SkillCatalogEntry:
    text = read_text(meta_path)
    meta = parse_meta_bullets(text)
    skill_id = str(meta.get("skill_id") or meta_path.parent.name)
    skill_doc_value = str(meta.get("skill_doc") or "./SKILL.md")
    skill_doc = (meta_path.parent / skill_doc_value).resolve()
    skill_text = read_text(skill_doc) if skill_doc.exists() else ""
    missing = _missing_skill_fields(meta, skill_doc.exists())
    knowledge_refs = scalar_list(meta, "knowledge_refs")
    capability_refs = scalar_list(meta, "capability_refs")
    closure = ClosureContract(
        closure_conditions=scalar_list(meta, "closure")
        or _section_bullets(skill_text, "Closure"),
        exit_enum=["completed", "blocked", "needs_input"],
        handoff_policy=str(meta.get("constraints") or "explicit handoff required"),
        worklist_policy=str(
            _nested_value(meta, "os_contract", "worklist_policy") or "required"
        ),
    )
    return SkillCatalogEntry(
        skill_id=skill_id,
        title=first_heading(skill_text or text, skill_id),
        summary=str(meta.get("summary") or first_paragraph(skill_text)),
        maturity=str(meta.get("maturity") or "unknown"),
        capabilities=[_xref_to_id(item) for item in capability_refs],
        intent=_derive_intent(meta),
        target_artifacts=_derive_target_artifacts(meta),
        applies_when=scalar_list(meta, "applies_when")
        or scalar_list(meta, "use_when"),
        not_for=scalar_list(meta, "not_for")
        or _split_constraints(str(meta.get("constraints") or "")),
        required_knowledge=[_knowledge_req(item) for item in knowledge_refs],
        required_tools=[_required_tool(item) for item in scalar_list(meta, "required_tools")],
        inputs=scalar_list(meta, "input"),
        outputs=scalar_list(meta, "output"),
        closure_contract=closure,
        meta_content=text,
        meta_links=markdown_xid_link_targets(text),
        skill_content=skill_text,
        skill_links=markdown_xid_link_targets(skill_text),
        path=relative_to_repo(skill_doc, root) if skill_doc.exists() else "",
        meta_path=relative_to_repo(meta_path, root),
        missing=missing,
    )


def _build_skills(root: Path) -> list[SkillCatalogEntry]:
    entries: list[SkillCatalogEntry] = []
    for meta_path in sorted((root / "skills").glob("**/meta.md")):
        entries.append(_build_skill_entry(root, meta_path))
    return entries


def _build_workflows(root: Path) -> list[WorkflowCatalogEntry]:
    flows_root = root / "flows"
    if not flows_root.exists():
        return []
    entries: list[WorkflowCatalogEntry] = []
    for path in sorted(flows_root.glob("**/*.yaml")):
        text = read_text(path)
        scalar = _yaml_top_scalars(text)
        owner = _yaml_nested_scalar(text, "owner", "primary")
        entry = scalar.get("entry")
        steps = _yaml_map_keys(text, "steps")
        sequence = _yaml_top_list(text, "sequence")
        capabilities = _yaml_values_for_key(text, "capability")
        schema_style = "unknown"
        if steps:
            schema_style = "deterministic_steps"
        elif sequence:
            schema_style = "legacy_sequence"
        missing: list[str] = []
        for field in ["flow_id", "name", "doc_xid"]:
            if not scalar.get(field):
                missing.append(field)
        if schema_style == "deterministic_steps" and not entry:
            missing.append("entry")
        entries.append(
            WorkflowCatalogEntry(
                flow_id=scalar.get("flow_id") or path.stem,
                name=scalar.get("name") or path.stem,
                doc_xid=scalar.get("doc_xid"),
                phase=scalar.get("phase"),
                owner=owner,
                path=relative_to_repo(path, root),
                schema_style=schema_style,  # type: ignore[arg-type]
                entry=entry,
                steps=steps,
                sequence=sequence,
                capabilities=capabilities,
                runs_after=_yaml_top_list(text, "runs_after"),
                runs_before=_yaml_top_list(text, "runs_before"),
                missing=missing,
            )
        )
    return entries


def _client_tool_distribution(root: Path) -> ClientToolDistribution:
    package_versions = {
        CLIENT_TOOL_PACKAGE_ID: CLIENT_TOOL_PACKAGE_VERSION,
        "xrefkit-client-tools": CLIENT_TOOL_PACKAGE_VERSION,
    }
    return ClientToolDistribution(
        package_id=CLIENT_TOOL_PACKAGE_ID,
        version=CLIENT_TOOL_PACKAGE_VERSION,
        execution_location="client",
        server_executes_tools=False,
        install_layout="write each file to the same relative path under the client-side target repository root",
        required_package_ids=sorted(package_versions),
        package_versions=package_versions,
        file_hash_algorithm="sha256",
        version_check_tool="check_client_tool_versions",
        materialization={
            "source": "xrefkit_mcp",
            "file_tool": "get_client_tool_file",
            "bundle_tool": "get_client_tool_bundle",
            "pip_package_tool": "get_client_tool_pip_package",
            "run_location": "client",
            "preserve_relative_paths": True,
        },
        update_policy={
            "check_on_startup": True,
            "install_when_missing": True,
            "update_when_version_mismatch": True,
            "server_executes_tools": False,
        },
        files=[
            ClientToolManifestEntry(
                path=file.path,
                kind=file.kind,
                content_hash=file.content_hash,
                size_bytes=file.size_bytes,
                run_hint=file.run_hint,
                resolver_tool="get_client_tool_file",
                resolver_argument="path",
            )
            for file in _client_tool_files(root)
        ],
        instructions=[
            "The MCP server only distributes these files; it must not execute them.",
            "Install files at their returned relative paths, typically under tools/ in the client-side repository.",
            "Run Python tools on the client side with the client repository root as the working directory.",
            "Some tools expect sibling tools modules, so preserve the returned directory layout.",
            "Some tools call external programs such as git, dotnet, npm, or project-specific commands; satisfy those prerequisites on the client side before execution.",
        ],
    )


def _client_obligations() -> list[ClientObligation]:
    return [
        ClientObligation(
            id="startup.first_call",
            level="must",
            applies_when="xrefkit_mcp_configured",
            statement="Call get_startup_context before task-specific routing.",
            enforcement_owner="client",
            verification="startup response is present before workflow, Skill, or knowledge routing",
        ),
        ClientObligation(
            id="content.mcp_only",
            level="must",
            applies_when="access_policy.mode == mcp_only",
            statement="Do not read XRefKit governance Markdown from a local filesystem checkout.",
            enforcement_owner="client",
            verification="XID-linked governance content is obtained through get_document_by_xid or get_skill",
        ),
        ClientObligation(
            id="links.resolve_by_xid",
            level="must",
            applies_when="transferred content contains links entries",
            statement="Resolve needed Markdown links by XID through get_document_by_xid.",
            enforcement_owner="client",
            verification="link resolver uses resolver_tool and resolver_argument from link metadata",
        ),
        ClientObligation(
            id="tools.materialize_from_mcp",
            level="must",
            applies_when="client executes XRefKit-distributed tools",
            statement="Fetch, materialize or install, and version-check client-side tools from XRefKit MCP before execution.",
            enforcement_owner="client",
            verification="check_client_tool_versions passes for the installed client-tool package versions",
        ),
        ClientObligation(
            id="tools.client_side_execution",
            level="must",
            applies_when="client runs XRefKit-distributed tools",
            statement="Run distributed tools only in the client execution environment; the MCP server does not execute them.",
            enforcement_owner="client",
            verification="tool execution occurs outside the XRefKit MCP server process",
        ),
        ClientObligation(
            id="context.no_duplicate_xid_body_per_session",
            level="must",
            applies_when="assembling model context",
            statement="Within a single client session, the client MUST NOT inject more than one full document body for the same repository_fingerprint, xid, and content_hash into the active model context. If the same XID version is needed again, the client MUST reference the existing session context entry by XID and content_hash instead of repeating the body.",
            enforcement_owner="client",
            verification="Prompt assembly maintains a session-visible XID index and records injected_xids, reused_xids, content_hash values, visibility status, and reuse reasons for each model turn.",
        ),
    ]


def _semantic_routing_references() -> list[dict[str, object]]:
    return [
        {
            "id": "skills",
            "purpose": "semantic Skill routing from user intent before procedure load",
            "summary_tool": "list_skills",
            "summary_arguments": {"include_content": False},
            "rank_tool": "rank_skills_for_purpose",
            "materialize_tool": "get_skill",
            "materialize_argument": "skill_id",
            "body_mode": "lazy",
        },
        {
            "id": "workflows",
            "purpose": "semantic workflow routing and workflow-order lookup",
            "summary_tool": "list_workflows",
            "materialize_tool": "get_document_by_xid",
            "materialize_argument": "doc_xid",
            "body_mode": "lazy",
        },
        {
            "id": "knowledge",
            "purpose": "domain-knowledge search after a task or Skill needs evidence",
            "summary_tool": "search_knowledge_catalog",
            "summary_arguments": {"limit": 10},
            "materialize_tool": "expand_knowledge",
            "materialize_argument": "xid",
            "body_mode": "lazy",
        },
        {
            "id": "tool_contracts",
            "purpose": "tool capability lookup when a task needs exact tool boundaries",
            "summary_tool": "list_tool_contracts",
            "body_mode": "metadata_only",
        },
    ]


def _client_tool_download_policy(entry: SkillCatalogEntry) -> dict[str, object]:
    required_client_tools = [
        item
        for item in entry.required_tools
        if item.get("execution_location") == "client" or item.get("name")
    ]
    return {
        "required": bool(required_client_tools),
        "required_client_tools": required_client_tools,
        "download_when": "after this Skill is selected for use and before executing its client-side required_tools",
        "do_not_download_at_startup": True,
        "manifest_tool": "get_client_tool_manifest",
        "package_tool": "get_client_tool_pip_package",
        "file_tool": "get_client_tool_file",
        "bundle_tool": "get_client_tool_bundle",
        "version_check_tool": "check_client_tool_versions",
    }


def _workflow_protocol() -> dict[str, object]:
    return {
        "source": "xrefkit_mcp",
        "routing": {
            "selection_basis": [
                "user intent",
                "startup load_order",
                "workflow catalog",
                "Skill catalog",
                "XID-linked evidence resolved through get_document_by_xid",
            ],
            "workflow_selection": "deterministic catalog metadata once selected; semantic selection may be performed by the client before execution",
            "skill_selection": "route by catalog metadata, then fetch selected Skill through get_skill",
        },
        "phase_order": [
            "startup",
            "planning",
            "execution",
            "check",
            "quality",
            "closure",
            "handoff",
        ],
        "role_ownership": {
            "executor": "Skill-specific execution role",
            "checker": "protocol-owned deterministic run-record verification",
            "quality_reviewer": "protocol-owned quality review role separate from executor",
            "handoff_owner": "protocol-owned handoff role",
        },
        "deterministic_checks": [
            "load_order is returned by get_startup_context",
            "XID links are resolved only through get_document_by_xid",
            "check phase is advanced by deterministic fm skill verify semantics",
            "content identity is content_hash; no duplicate document version field is emitted",
        ],
        "non_deterministic_decisions": [
            "semantic workflow or Skill routing from user intent",
            "quality judgment after deterministic checks pass",
            "task-specific evidence sufficiency judgment",
        ],
    }


def _context_injection_policy() -> dict[str, object]:
    return {
        "model_context_format": "plain_text",
        "model_context_source": "startup_contract_pack.body",
        "do_not_inject_raw_startup_json": True,
        "default_document_body_mode": "lazy",
        "default_nonstartup_document_body_mode": "lazy",
        "startup_reference_prompt_mode": "required_startup_contract_pack",
        "startup_contract_pack_visible_by_default": True,
        "startup_reference_body_visible_by_default": False,
        "materialize_does_not_imply_prompt_injection": True,
        "body_injection_unit": "xid_document",
        "body_visible_by_default": False,
        "metadata_visible_by_default": [
            "xid",
            "title",
            "summary",
            "layer",
            "required_at_init",
            "content_hash",
            "links",
            "cache_status",
            "client_cache_status",
        ],
        "inject_body_when": [
            "the active task explicitly requires that XID",
            "the selected workflow or Skill declares that XID as required evidence",
            "the model requests a linked XID that is needed to resolve a concrete uncertainty",
            "a closure, safety, or verification check depends on the exact wording of that XID",
            "the user explicitly asks to inspect, quote, edit, or verify that document",
        ],
        "do_not_inject_body_when": [
            "the XID is only present as a related link",
            "the summary is sufficient for routing",
            "the document is cached only for future resolution",
            "the document belongs to a lower-layer context that is not active for the current task",
        ],
    }


def _session_context_deduplication() -> dict[str, object]:
    return {
        "scope": "single_client_session",
        "dedupe_key": [
            "repository_fingerprint",
            "xid",
            "content_hash",
        ],
        "active_model_context_cardinality": "at_most_one_body_per_dedupe_key",
        "materialize_does_not_imply_duplicate_injection": True,
        "on_repeated_xid_same_hash": "reference_existing_session_context_entry",
        "on_repeated_xid_different_hash": "treat_as_version_change_and_replace_or_escalate",
        "reinject_body_only_when": [
            "the previous body is no longer visible in the active model context",
            "the content_hash changed and the new version is selected",
            "the client intentionally rebuilds the active context after compaction",
        ],
        "trace_required": True,
    }


def _client_tool_files(root: Path) -> list[ClientToolFile]:
    tools_root = root / "tools"
    if not tools_root.exists():
        return []
    paths = sorted(tools_root.glob("**/*.py"))
    support_paths = [
        path
        for path in sorted((tools_root / "profiles").glob("**/*"))
        if path.is_file()
    ]
    readme = tools_root / "README.md"
    if readme.exists():
        support_paths.append(readme)

    result: list[ClientToolFile] = []
    for path in [*paths, *support_paths]:
        rel = relative_to_repo(path, root)
        text = read_text(path)
        kind = _client_tool_kind(path)
        result.append(
            ClientToolFile(
                path=rel,
                kind=kind,
                content=text,
                content_hash=stable_hash(text),
                size_bytes=len(text.encode("utf-8")),
                run_hint=f"python {rel}" if kind == "python" else None,
                imports=_python_imports(text) if kind == "python" else [],
                links=markdown_xid_link_targets(text),
            )
        )
    return result


def _client_tool_pip_package(root: Path) -> ClientToolPipPackage:
    files = _client_tool_files(root)
    package_root = f"xrefkit-client-tools-{CLIENT_TOOL_PACKAGE_VERSION}"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            f"{package_root}/pyproject.toml",
            _client_tools_pyproject(files),
        )
        archive.writestr(
            f"{package_root}/README.md",
            _client_tools_readme(),
        )
        archive.writestr(
            f"{package_root}/tools/__init__.py",
            '"""Client-side XRefKit deterministic tools."""\n',
        )
        for file in files:
            archive.writestr(f"{package_root}/{file.path}", file.content)
    content = buffer.getvalue()
    encoded = base64.b64encode(content).decode("ascii")
    return ClientToolPipPackage(
        filename=f"xrefkit-client-tools-{CLIENT_TOOL_PACKAGE_VERSION}.zip",
        package_id="xrefkit-client-tools",
        version=CLIENT_TOOL_PACKAGE_VERSION,
        package_format="zip-sdist",
        install_command=f"python -m pip install xrefkit-client-tools-{CLIENT_TOOL_PACKAGE_VERSION}.zip",
        content_base64=encoded,
        content_hash=hashlib_sha256_bytes(content),
        size_bytes=len(content),
        warnings=[
            "This package installs a top-level tools package to preserve existing XRefKit imports such as tools.error_policy_locator.",
            "Install in a project virtual environment to avoid conflicts with any unrelated package named tools.",
            "The package contains Python tools only; C# tools/structure_graph is not bundled.",
            "The MCP server only distributes the package; tool execution is client-side.",
        ],
    )


def _client_tools_pyproject(files: list[ClientToolFile]) -> str:
    scripts: list[str] = []
    for file in files:
        if file.kind != "python" or "def main" not in file.content:
            continue
        module = file.path.removesuffix(".py").replace("/", ".")
        script_name = "xrefkit-" + Path(file.path).stem.replace("_", "-")
        scripts.append(f'{script_name} = "{module}:main"')
    scripts_block = "\n".join(sorted(scripts))
    return f"""[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "xrefkit-client-tools"
version = "{CLIENT_TOOL_PACKAGE_VERSION}"
description = "Client-side deterministic Python tools distributed from XRefKit MCP"
readme = "README.md"
requires-python = ">=3.11"
dependencies = []

[tool.setuptools.packages.find]
include = ["tools*"]

[project.scripts]
{scripts_block}
"""


def _client_tools_readme() -> str:
    return """# XRefKit Client Tools

This package is generated by XRefKit MCP and installs the Python files from
`tools/` for client-side execution.

The MCP server does not execute these tools. Run them in the client-side target
repository where the analyzed source files exist.

Examples:

```powershell
python -m tools.cs_scope_probe --target .
xrefkit-cs-scope-probe --target .
```

Some tools require external programs such as git, dotnet, npm, or precomputed
`tools/structure_graph` output.
"""


def hashlib_sha256_bytes(content: bytes) -> str:
    import hashlib

    return hashlib.sha256(content).hexdigest()


def _client_tool_kind(path: Path) -> str:
    if path.suffix == ".py":
        return "python"
    if path.name.lower() == "readme.md":
        return "documentation"
    return "support"


def _python_imports(text: str) -> list[str]:
    imports: list[str] = []
    for match in IMPORT_RE.finditer(text):
        module = match.group(1)
        if module not in imports:
            imports.append(module)
    return imports


def _runtime_role_contract() -> RuntimeRoleContract:
    return RuntimeRoleContract(
        roles={
            "executor": "advances the execution phase and performs assigned work items",
            "checker": "advances deterministic check/progression verification and must differ from executor",
            "quality_reviewer": "advances quality acceptance for standard/heavy work and must differ from executor",
            "handoff_owner": "advances explicit handoff phase and unresolved-item transfer",
        },
        phases=["startup", "planning", "execution", "check", "quality", "closure", "handoff"],
        statuses=["pending", "in_progress", "done", "blocked", "unknown", "escalated"],
        invariants=[
            "Skill execution starts through fm skill run before opening SKILL.md",
            "execution/check/quality roles are separated from the executor role",
            "check is deterministic progression verification via fm skill verify",
            "quality is a separate acceptance axis for standard/heavy work",
            "unknowns must resolve before closure; risks must resolve or escalate",
            "closure requires work items plus output and evidence artifacts",
            "workflow steps transition through gates, not through bare model judgment",
        ],
        required_commands=[
            "python -m fm skill run --meta <path-to-meta.md> --task \"<task>\" --json",
            "python -m fm skill workitem --log <run-log> --item <id> --status <status> --role <assigned-role>",
            "python -m fm skill artifact --log <run-log> --artifact <id> --kind <kind> --target <target> --status <status> --role <assigned-role>",
            "python -m fm skill concern --log <run-log> --concern <id> --kind <unknown|risk|judgment> --status <status> --role <assigned-role>",
            "python -m fm skill verify --log <run-log>",
            "python -m fm skill close --log <run-log>",
        ],
        source_xids=["B7A2C94F0E61", "6D2E4A9C0B71", "4C7E9A2B1D63", "1F93A7C24010"],
    )


def _missing_skill_fields(meta: dict[str, object], has_skill_doc: bool) -> list[str]:
    required = [
        "skill_id",
        "summary",
        "maturity",
        "knowledge_refs",
        "capability_refs",
        "input",
        "output",
    ]
    missing = [field for field in required if not meta.get(field)]
    for field in ["intent", "target_artifacts", "applies_when", "not_for", "required_tools"]:
        if not meta.get(field):
            missing.append(field)
    if not has_skill_doc:
        missing.append("skill_doc")
    return missing


def _derive_intent(meta: dict[str, object]) -> list[str]:
    explicit = scalar_list(meta, "intent")
    if explicit:
        return explicit
    tags = scalar_list(meta, "tags")
    use_when = str(meta.get("use_when") or "")
    values = [tag for tag in tags if tag in {"review", "design", "routing", "quality"}]
    if "review" in use_when.lower() and "review" not in values:
        values.append("review")
    if "route" in use_when.lower() and "routing" not in values:
        values.append("routing")
    return values


def _derive_target_artifacts(meta: dict[str, object]) -> list[str]:
    explicit = scalar_list(meta, "target_artifacts")
    if explicit:
        return explicit
    haystack = " ".join(
        [str(meta.get("use_when") or ""), str(meta.get("input") or ""), *scalar_list(meta, "tags")]
    ).lower()
    targets: list[str] = []
    for needle, target in [
        ("c#", "csharp_source"),
        ("dotnet", "dotnet_source"),
        ("ddl", "ddl"),
        ("api", "api_contract"),
        ("screen", "ui_spec"),
        ("design", "design_artifact"),
        ("code", "source_code"),
    ]:
        if needle in haystack and target not in targets:
            targets.append(target)
    return targets


def _split_constraints(value: str) -> list[str]:
    if not value:
        return []
    pieces = re.split(r";|,|—|--", value)
    return [piece.strip() for piece in pieces if piece.strip()]


def _knowledge_req(ref: str) -> dict[str, object]:
    xid_match = re.search(r"#xid-([A-Za-z0-9]+)", ref)
    return {
        "xid": xid_match.group(1) if xid_match else ref,
        "version": 1,
        "required_when": "declared by Skill meta knowledge_refs",
        "detail_policy": "expand_on_demand",
    }


def _required_tool(name: str) -> dict[str, object]:
    if name.startswith("xref."):
        return {
            "tool_id": name,
            "required_when": "declared by Skill meta required_tools",
        }
    return {
        "name": name,
        "execution_location": "client",
        "required_when": "declared by Skill meta required_tools",
    }


def _xref_to_id(ref: str) -> str:
    xid_match = re.search(r"#xid-([A-Za-z0-9]+)", ref)
    return xid_match.group(1) if xid_match else ref


def _section_bullets(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    in_section = False
    result: list[str] = []
    for line in lines:
        if line.startswith("## "):
            in_section = line.strip("# ").strip().lower() == heading.lower()
            continue
        if in_section and line.startswith("- "):
            result.append(line[2:].strip())
    return result


def _nested_value(meta: dict[str, object], _parent: str, _key: str) -> str | None:
    # Current XRefKit meta files use prose-like nested bullets. They are kept
    # opaque by the lightweight parser, so return None until a structured field
    # exists in the source repository.
    return None


def _yaml_top_scalars(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in text.splitlines():
        if raw.startswith(" ") or not raw.strip() or raw.lstrip().startswith("#"):
            continue
        match = re.match(r"^([A-Za-z0-9_]+):\s*(.+?)\s*$", raw)
        if match and not match.group(2).startswith("["):
            result[match.group(1)] = match.group(2).strip().strip('"')
    return result


def _yaml_nested_scalar(text: str, parent: str, key: str) -> str | None:
    in_parent = False
    for raw in text.splitlines():
        if re.match(rf"^{re.escape(parent)}:\s*$", raw):
            in_parent = True
            continue
        if in_parent and raw and not raw.startswith(" "):
            return None
        if in_parent:
            match = re.match(rf"^\s+{re.escape(key)}:\s*(.+?)\s*$", raw)
            if match:
                return match.group(1).strip().strip('"')
    return None


def _yaml_top_list(text: str, key: str) -> list[str]:
    in_list = False
    result: list[str] = []
    for raw in text.splitlines():
        if re.match(rf"^{re.escape(key)}:\s*$", raw):
            in_list = True
            continue
        if in_list and raw and not raw.startswith(" "):
            break
        if in_list:
            match = re.match(r"^\s+-\s+(.+?)\s*$", raw)
            if match:
                result.append(match.group(1).strip().strip('"'))
    return result


def _yaml_map_keys(text: str, key: str) -> list[str]:
    in_map = False
    result: list[str] = []
    for raw in text.splitlines():
        if re.match(rf"^{re.escape(key)}:\s*$", raw):
            in_map = True
            continue
        if in_map and raw and not raw.startswith(" "):
            break
        if in_map:
            match = re.match(r"^\s{2}([A-Za-z0-9_]+):\s*$", raw)
            if match:
                result.append(match.group(1))
    return result


def _yaml_values_for_key(text: str, key: str) -> list[str]:
    values: list[str] = []
    for raw in text.splitlines():
        match = re.match(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", raw)
        if match:
            values.append(match.group(1).strip().strip('"'))
    return list(dict.fromkeys(values))


def _rank_entries(query: str, entries: list[KnowledgeCatalogEntry]) -> list[KnowledgeCatalogEntry]:
    query_tokens = _tokens(query)
    return sorted(
        entries,
        key=lambda entry: (
            len(query_tokens & _tokens(" ".join([entry.title, entry.summary, entry.domain]))),
            entry.title,
        ),
        reverse=True,
    )


def _tokens(value: str) -> set[str]:
    normalized = (
        value.lower()
        .replace("_", " ")
        .replace("c#", "csharp")
        .replace(".net", "dotnet")
        .replace("non-roslyn", "roslyn")
    )
    tokens = {match.group(0).lower() for match in TOKEN_RE.finditer(normalized)}
    if "roslyn" in tokens:
        tokens.add("diagnostics")
    if "csharp" in tokens:
        tokens.add("c#")
    return tokens


def _matched_values(
    query_tokens: set[str], values: list[str], use_stop_words: bool = False
) -> list[str]:
    matched: list[str] = []
    for value in values:
        value_tokens = _tokens(value)
        if use_stop_words:
            value_tokens = value_tokens - STOP_TOKENS
            effective_query = query_tokens - STOP_TOKENS
        else:
            effective_query = query_tokens
        if effective_query & value_tokens:
            matched.append(value)
    return matched


def _overlap_count(query_tokens: set[str], values: list[str]) -> int:
    value_tokens = set().union(*(_tokens(value) for value in values)) if values else set()
    return len((query_tokens - STOP_TOKENS) & (value_tokens - STOP_TOKENS))
