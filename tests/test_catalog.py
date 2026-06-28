from __future__ import annotations

import tempfile
import unittest
import base64
import io
import zipfile
from pathlib import Path

from xrefkit_mcp.catalog import (
    CACHE_MAX_VERSION_PAYLOAD_RATIO,
    XRefCatalog,
    _conditional_document_response,
    _document_cache_policy,
)
from xrefkit_mcp.schemas import ToolContract, XRefDocument


REPOSITORY_FINGERPRINT = "a" * 32


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_dir.name)
        write(
            self.repo / "knowledge" / "organization" / "rules.md",
            """<!-- xid: ABC123 -->
<a id="xid-ABC123"></a>

# Context Rules

Use this when external input is loaded.
""",
        )
        write(
            self.repo / "skills" / "sample" / "meta.md",
            """<!-- xid: SKILLMETA -->
# Skill Meta: sample_review

- skill_id: `sample_review`
- summary: review sample source
- use_when: user asks to review sample code
- intent:
  - review explicit sample source behavior
- applies_when:
  - sample source needs catalog-driven review
- target_artifacts:
  - sample source findings
- not_for:
  - formatting-only edits
- required_tools:
  - fm skill run
  - fm skill verify
- input: source path
- output: findings
- maturity: `trial`
- constraints: do not format code
- tags: `review`, `quality`
- skill_doc: `./SKILL.md`
- capability_refs:
  - `../../capabilities/quality/sample.md#xid-CAP1`
- knowledge_refs:
  - `../../knowledge/organization/rules.md#xid-ABC123`
""",
        )
        write(
            self.repo / "skills" / "sample" / "SKILL.md",
            """<!-- xid: SKILLDOC -->
# Skill: sample_review

Use [Context Rules](../../knowledge/organization/rules.md#xid-ABC123).

## Closure

- return findings
""",
        )
        for rel_path, xid, title in [
            ("agent/000_agent_entry.md", "0B5C58B5E5B2", "Agent Entry"),
            ("docs/core/models/017_base_and_xref_layering.md", "5A1C8E4D2F90", "Base Control and Xref Routing Layers"),
            ("docs/core/contracts/011_startup_xref_routing.md", "6C0B62D6366A", "Startup Xref Routing Policy"),
            ("docs/core/contracts/016_uncertainty_protocol.md", "8A666C1FD121", "Uncertainty Protocol"),
            ("docs/core/contracts/053_context_direction_security_guard.md", "A7F3C92D4E11", "Context Direction Security Guard"),
            ("docs/core/contracts/015_shared_memory_operations.md", "4A423E72D2ED", "Shared Memory Operations"),
        ]:
            detail = "\n".join(
                "Detailed startup governance content used to exercise conditional retrieval."
                for _ in range(20)
            )
            write(
                self.repo / rel_path,
                f"""<!-- xid: {xid} -->
<a id="xid-{xid}"></a>

# {title}

Required startup reference. See [Uncertainty](016_uncertainty_protocol.md#xid-8A666C1FD121).

{detail}
""",
            )
        write(
            self.repo / "flows" / "sample_workflow.yaml",
            """flow_id: FLOW-SAMPLE
name: sample_workflow
doc_xid: FLOWDOC
phase: normal
owner:
  primary: sample_group
runs_after:
  - FLOW-UPSTREAM
runs_before:
  - FLOW-DOWNSTREAM
entry: draft
steps:
  draft:
    capability: CAP-SAMPLE-001
    on:
      Go: COMPLETE
      _invalid_or_absent: ABORT
""",
        )
        write(
            self.repo / "tools" / "sample_tool.py",
            """from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ok", action="store_true")
    return 0 if parser.parse_args().ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
""",
        )
        write(
            self.repo / "tools" / "profiles" / "sample.editorconfig",
            "root = true\n",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_builds_read_only_catalog(self) -> None:
        catalog = XRefCatalog.build(self.repo)

        self.assertTrue(catalog.catalog_version)
        self.assertEqual(len(catalog.knowledge), 1)
        self.assertEqual(len(catalog.skills), 1)
        self.assertEqual(
            catalog.skills[0].intent,
            ["review explicit sample source behavior"],
        )
        self.assertEqual(
            catalog.skills[0].applies_when,
            ["sample source needs catalog-driven review"],
        )
        self.assertEqual(catalog.skills[0].target_artifacts, ["sample source findings"])
        self.assertEqual(catalog.skills[0].not_for, ["formatting-only edits"])
        self.assertEqual(
            catalog.skills[0].required_tools,
            [
                {
                    "name": "fm skill run",
                    "execution_location": "client",
                    "required_when": "declared by Skill meta required_tools",
                },
                {
                    "name": "fm skill verify",
                    "execution_location": "client",
                    "required_when": "declared by Skill meta required_tools",
                },
            ],
        )
        self.assertTrue(all(tool.side_effects == "none" for tool in catalog.tools))
        self.assertTrue(
            all(tool.to_dict()["input_json_schema"]["type"] == "object" for tool in catalog.tools)
        )
        self.assertIn("Skill: sample_review", catalog.skills[0].skill_content)
        self.assertEqual(catalog.skills[0].skill_links[0]["xid"], "ABC123")
        self.assertEqual(catalog.skills[0].skill_links[0]["resolver_tool"], "get_document_by_xid")
        self.assertEqual(
            catalog.get_repository_identity()["cache_namespace"],
            catalog.repository_fingerprint,
        )

    def test_expands_knowledge_by_xid(self) -> None:
        catalog = XRefCatalog.build(self.repo)

        expanded = catalog.expand_knowledge("ABC123")

        self.assertEqual(expanded["entry"]["title"], "Context Rules")
        self.assertIn("external input", expanded["content"])

    def test_ranks_skills_without_selecting_one(self) -> None:
        catalog = XRefCatalog.build(self.repo)

        result = catalog.rank_skills_for_purpose("review sample code", limit=1)[0]

        self.assertEqual(result["skill_id"], "sample_review")
        self.assertGreater(result["score"], 0)
        self.assertIs(result["execution_readiness"]["runnable"], True)
        self.assertEqual(
            result["closure_preview"]["exit_enum"],
            ["completed", "blocked", "needs_input"],
        )

    def test_get_skill_returns_transferred_skill_files_and_links(self) -> None:
        catalog = XRefCatalog.build(self.repo)

        skill = catalog.get_skill("sample_review")

        self.assertIn("Skill Meta: sample_review", skill["meta_content"])
        self.assertIn("Skill: sample_review", skill["skill_content"])
        self.assertEqual(skill["skill_links"][0]["xid"], "ABC123")
        self.assertEqual(skill["skill_links"][0]["resolver_tool"], "get_document_by_xid")

    def test_cache_aware_skill_returns_conditional_xid_documents(self) -> None:
        catalog = XRefCatalog.build(self.repo)
        first = catalog.get_skill("sample_review", {})
        versions = {
            document["xid"]: document["content_hash"]
            for document in first["documents"]
            if document["cache_policy"]["cache_recommended"]
        }

        cached = catalog.get_skill("sample_review", versions)

        self.assertIsNone(cached["meta_content"])
        self.assertIsNone(cached["skill_content"])
        self.assertEqual(len(cached["documents"]), 2)
        for document in cached["documents"]:
            if document["xid"] in versions:
                self.assertEqual(document["cache_status"], "not_modified")
                self.assertNotIn("content", document)

    def test_list_skills_can_exclude_document_bodies(self) -> None:
        catalog = XRefCatalog.build(self.repo)

        skill = catalog.list_skills(include_content=False)[0]

        self.assertIsNone(skill["meta_content"])
        self.assertIsNone(skill["skill_content"])
        self.assertEqual(
            {document["xid"] for document in skill["document_versions"]},
            {"SKILLMETA", "SKILLDOC"},
        )

    def test_rejects_server_tool_with_side_effects(self) -> None:
        contract = ToolContract(
            tool_id="bad.write",
            provider="test",
            version="1",
            execution_location="server",
            side_effects="repo_write",
            input_schema={},
            output_schema={},
            requires_workspace=True,
            required_when="never",
        )

        with self.assertRaises(ValueError):
            contract.validate()

    def test_startup_context_lists_base_control_references(self) -> None:
        catalog = XRefCatalog.build(self.repo)

        context = catalog.get_startup_context()
        xids = [reference["xid"] for reference in context["references"]]

        self.assertEqual(context["link_resolution"]["resolver_tool"], "get_document_by_xid")
        self.assertEqual(context["access_policy"]["mode"], "mcp_only")
        self.assertEqual(context["access_policy"]["source_of_truth"], "xrefkit_mcp")
        self.assertIn(
            "get_startup_context",
            context["access_policy"]["required_tools"]["startup"],
        )
        self.assertTrue(
            any("get_document_by_xid" in item for item in context["client_instructions"])
        )
        self.assertTrue(
            any("MCP-only mode is active" in item for item in context["client_instructions"])
        )
        self.assertIn("8A666C1FD121", xids)
        self.assertIn("0B5C58B5E5B2", xids)
        self.assertEqual(context["missing"], [])
        self.assertEqual(context["references"][0]["layer"], "base_control")
        self.assertIn("Required startup reference.", context["references"][0]["content"])
        first_link = context["references"][0]["links"][0]
        self.assertEqual(first_link["xid"], "8A666C1FD121")
        self.assertEqual(first_link["resolver_tool"], "get_document_by_xid")
        self.assertEqual(first_link["resolver_argument"], "xid")
        self.assertEqual(context["workflows"][0]["flow_id"], "FLOW-SAMPLE")
        self.assertIn("checker", context["runtime_role_contract"]["roles"])
        self.assertIn(
            "check is deterministic progression verification via fm skill verify",
            context["runtime_role_contract"]["invariants"],
        )
        obligation_ids = {item["id"] for item in context["client_obligations"]}
        self.assertIn("startup.first_call", obligation_ids)
        self.assertIn("content.mcp_only", obligation_ids)
        self.assertIn("tools.materialize_from_mcp", obligation_ids)
        self.assertEqual(
            context["client_tool_distribution"]["materialization"]["bundle_tool"],
            "get_client_tool_bundle",
        )
        self.assertIs(
            context["client_tool_distribution"]["update_policy"]["check_on_startup"],
            True,
        )

    def test_startup_context_omits_cached_reference_bodies(self) -> None:
        catalog = XRefCatalog.build(self.repo)
        first = catalog.get_startup_context()
        versions = {
            reference["xid"]: reference["content_hash"]
            for reference in first["references"]
        }

        cached = catalog.get_startup_context(versions)

        self.assertTrue(
            all(reference["cache_status"] == "not_modified" for reference in cached["references"])
        )
        self.assertTrue(
            all(reference["content_omitted"] for reference in cached["references"])
        )
        self.assertTrue(
            all(reference["content"] is None for reference in cached["references"])
        )

    def test_startup_context_resolves_reference_after_document_move(self) -> None:
        source = self.repo / "docs" / "core" / "contracts" / "016_uncertainty_protocol.md"
        target = self.repo / "docs" / "core" / "contracts" / "uncertainty_protocol.md"
        source.rename(target)

        context = XRefCatalog.build(self.repo).get_startup_context()
        uncertainty = next(
            reference
            for reference in context["references"]
            if reference["xid"] == "8A666C1FD121"
        )

        self.assertEqual(
            uncertainty["path"],
            "docs/core/contracts/uncertainty_protocol.md",
        )
        self.assertEqual(context["missing"], [])

    def test_lists_workflows(self) -> None:
        catalog = XRefCatalog.build(self.repo)

        workflows = catalog.list_workflows()

        self.assertEqual(workflows[0]["schema_style"], "deterministic_steps")
        self.assertEqual(workflows[0]["entry"], "draft")
        self.assertEqual(workflows[0]["capabilities"], ["CAP-SAMPLE-001"])

    def test_resolves_any_managed_document_by_xid(self) -> None:
        catalog = XRefCatalog.build(self.repo)

        document = catalog.get_document_by_xid("8A666C1FD121")

        self.assertEqual(document["path"], "docs/core/contracts/016_uncertainty_protocol.md")
        self.assertIn("# Uncertainty Protocol", document["content"])
        self.assertEqual(document["version"], document["content_hash"])
        self.assertIs(document["cache_policy"]["cache_recommended"], True)

    def test_conditional_document_resolution_omits_unchanged_content(self) -> None:
        catalog = XRefCatalog.build(self.repo)
        document = catalog.get_document_by_xid("8A666C1FD121")

        unchanged = catalog.get_document_by_xid(
            "8A666C1FD121",
            document["content_hash"],
        )
        stale = catalog.get_document_by_xid("8A666C1FD121", "stale-version")

        self.assertEqual(unchanged["cache_status"], "not_modified")
        self.assertIs(unchanged["content_omitted"], True)
        self.assertNotIn("content", unchanged)
        self.assertEqual(stale["cache_status"], "modified")
        self.assertIn("# Uncertainty Protocol", stale["content"])

    def test_cache_policy_bypasses_when_version_payload_is_not_smaller(self) -> None:
        document = XRefDocument(
            xid="A",
            title="",
            path="a",
            summary="",
            content="x",
            links=[],
            content_hash="0" * 64,
        )

        policy = _document_cache_policy(document, REPOSITORY_FINGERPRINT)

        self.assertEqual(policy["maximum_ratio"], CACHE_MAX_VERSION_PAYLOAD_RATIO)
        self.assertIs(policy["cache_recommended"], False)

        first = _conditional_document_response(
            document,
            None,
            REPOSITORY_FINGERPRINT,
        )
        conditional = _conditional_document_response(
            document,
            document.content_hash,
            REPOSITORY_FINGERPRINT,
        )

        self.assertEqual(first["cache_status"], "miss")
        self.assertIs(first["cache_policy"]["cache_recommended"], False)
        self.assertEqual(conditional["cache_status"], "bypassed")
        self.assertIn("content", conditional)

    def test_distributes_client_side_python_tools_without_server_execution(self) -> None:
        catalog = XRefCatalog.build(self.repo)

        manifest = catalog.get_client_tool_manifest()
        file_paths = [file["path"] for file in manifest["files"]]
        tool_file = catalog.get_client_tool_file("tools/sample_tool.py")
        bundle = catalog.get_client_tool_bundle()

        self.assertEqual(manifest["execution_location"], "client")
        self.assertEqual(manifest["version"], "0.1.0")
        self.assertIs(manifest["server_executes_tools"], False)
        self.assertEqual(manifest["file_hash_algorithm"], "sha256")
        self.assertEqual(manifest["version_check_tool"], "check_client_tool_versions")
        self.assertIn("xrefkit-client-tools", manifest["required_package_ids"])
        self.assertEqual(manifest["package_versions"]["xrefkit-client-tools"], "0.1.0")
        self.assertEqual(
            manifest["materialization"]["pip_package_tool"],
            "get_client_tool_pip_package",
        )
        self.assertIs(manifest["update_policy"]["update_when_version_mismatch"], True)
        self.assertIn("tools/sample_tool.py", file_paths)
        self.assertIn("tools/profiles/sample.editorconfig", file_paths)
        self.assertEqual(tool_file["kind"], "python")
        self.assertIn("argparse", tool_file["imports"])
        self.assertIn("argparse.ArgumentParser", tool_file["content"])
        self.assertGreaterEqual(len(bundle["files"]), 2)

    def test_builds_pip_installable_client_tool_package(self) -> None:
        catalog = XRefCatalog.build(self.repo)

        package = catalog.get_client_tool_pip_package()
        data = base64.b64decode(package["content_base64"])
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            pyproject = archive.read(
                "xrefkit-client-tools-0.1.0/pyproject.toml"
            ).decode("utf-8")

        self.assertEqual(package["package_format"], "zip-sdist")
        self.assertEqual(package["version"], "0.1.0")
        self.assertIn("python -m pip install", package["install_command"])
        self.assertIn("xrefkit-client-tools-0.1.0/tools/sample_tool.py", names)
        self.assertIn("xrefkit-client-tools-0.1.0/tools/__init__.py", names)
        self.assertIn("xrefkit-sample-tool", pyproject)

    def test_checks_client_tool_versions(self) -> None:
        catalog = XRefCatalog.build(self.repo)

        ok = catalog.check_client_tool_versions(
            {
                "xrefkit-client-python-tools": "0.1.0",
                "xrefkit-client-tools": "0.1.0",
            }
        )
        mismatch = catalog.check_client_tool_versions(
            {"xrefkit-client-python-tools": "0.0.1"}
        )

        self.assertIs(ok["ok"], True)
        self.assertIs(mismatch["ok"], False)
        self.assertTrue(any(row["status"] == "mismatch" for row in mismatch["results"]))
        self.assertTrue(any(row["status"] == "missing" for row in mismatch["results"]))

    def test_tool_contracts_describe_response_envelope_and_json_schema(self) -> None:
        catalog = XRefCatalog.build(self.repo)

        contracts = {contract["tool_id"]: contract for contract in catalog.list_tool_contracts()}

        self.assertEqual(
            contracts["xref.list_skills"]["response_envelope"],
            "mcp_result_array",
        )
        self.assertEqual(
            contracts["xref.get_startup_context"]["response_envelope"],
            "direct_object",
        )
        self.assertEqual(
            contracts["xref.get_document_by_xid"]["input_json_schema"]["properties"]["xid"]["type"],
            "string",
        )
        self.assertNotIn(
            "known_version",
            contracts["xref.get_document_by_xid"]["input_json_schema"]["required"],
        )


if __name__ == "__main__":
    unittest.main()
