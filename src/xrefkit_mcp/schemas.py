from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


ExecutionLocation = Literal["server", "client"]
SideEffects = Literal["none", "repo_write", "external_write", "unknown"]


@dataclass(frozen=True)
class ToolContract:
    tool_id: str
    provider: str
    version: str
    execution_location: ExecutionLocation
    side_effects: SideEffects
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    requires_workspace: bool
    required_when: str
    enforced_fields: tuple[str, ...] = ("execution_location", "side_effects")

    def validate(self) -> None:
        if self.execution_location == "server" and self.side_effects != "none":
            raise ValueError(
                f"server tool {self.tool_id!r} must declare side_effects='none'"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeCatalogEntry:
    xid: str
    version: int
    content_hash: str
    revised_at: str | None
    title: str
    domain: str
    summary: str
    applies_when: list[str]
    requires_knowledge: list[str]
    related_skills: list[str]
    related_capabilities: list[str]
    path: str
    expandable: bool = True
    missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClosureContract:
    closure_conditions: list[str]
    exit_enum: list[str]
    handoff_policy: str
    worklist_policy: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SkillCatalogEntry:
    skill_id: str
    title: str
    summary: str
    maturity: str
    capabilities: list[str]
    intent: list[str]
    target_artifacts: list[str]
    applies_when: list[str]
    not_for: list[str]
    required_knowledge: list[dict[str, Any]]
    required_tools: list[dict[str, Any]]
    inputs: list[str]
    outputs: list[str]
    closure_contract: ClosureContract
    meta_content: str
    meta_links: list[dict[str, str]]
    skill_content: str
    skill_links: list[dict[str, str]]
    path: str
    meta_path: str
    missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["closure_contract"] = self.closure_contract.to_dict()
        return data


@dataclass(frozen=True)
class SkillRankResult:
    skill_id: str
    matched_facets: list[str]
    closure_preview: ClosureContract
    required_knowledge: list[dict[str, Any]]
    execution_readiness: dict[str, Any]
    score: float

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["closure_preview"] = self.closure_preview.to_dict()
        return data


@dataclass(frozen=True)
class StartupReference:
    xid: str
    title: str
    path: str
    layer: Literal["base_control", "xref_routing"]
    required_at_init: bool
    reason: str
    summary: str
    content: str
    links: list[dict[str, str]]
    content_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class XRefDocument:
    xid: str
    title: str
    path: str
    summary: str
    content: str
    links: list[dict[str, str]]
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowCatalogEntry:
    flow_id: str
    name: str
    doc_xid: str | None
    phase: str | None
    owner: str | None
    path: str
    schema_style: Literal["deterministic_steps", "legacy_sequence", "unknown"]
    entry: str | None
    steps: list[str]
    sequence: list[str]
    capabilities: list[str]
    runs_after: list[str]
    runs_before: list[str]
    missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeRoleContract:
    roles: dict[str, str]
    phases: list[str]
    statuses: list[str]
    invariants: list[str]
    required_commands: list[str]
    source_xids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StartupContext:
    catalog_version: str
    client_instructions: list[str]
    link_resolution: dict[str, str]
    load_order: list[str]
    references: list[StartupReference]
    workflows: list[WorkflowCatalogEntry]
    runtime_role_contract: RuntimeRoleContract
    missing: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "catalog_version": self.catalog_version,
            "client_instructions": self.client_instructions,
            "link_resolution": self.link_resolution,
            "load_order": self.load_order,
            "references": [reference.to_dict() for reference in self.references],
            "workflows": [workflow.to_dict() for workflow in self.workflows],
            "runtime_role_contract": self.runtime_role_contract.to_dict(),
            "missing": self.missing,
        }
