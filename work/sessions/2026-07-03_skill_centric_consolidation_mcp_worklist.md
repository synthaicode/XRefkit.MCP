# Skill-Centric Consolidation — MCP Worklist

## Scope

Changes to **XRefKit.MCP** to match the skill-centric architecture. Companion:
the XRefKit worklist in `XRefKit/work/sessions/`.

Design sources (in the XRefKit repo):

- `docs/designs/084_skill_centric_mcp_catalog_design.md` (xid 261B40E5C76B) — MCP side
- `docs/designs/083_skill_centric_architecture_consolidation.md` (xid 9DF3B80F9CBE)
- `docs/designs/082_client_authoring_and_unified_supply_design.md` (xid B0572E20DFBA)

Branch (suggested): `codex/skill-centric-consolidation-mcp`

## Ordering

Superset-first, per the 084 phase table (A→E). Tolerant additions land before the
XRefKit-side removals; catalog/tool removals land after the XRefKit-side content
is removed. Keep existing tool names and response shapes compatible during
transition.

## Work Items

### MCP-101 (Phase A): Tolerate absent `flows/` and `capabilities/`

Status: done — tolerance already holds via the `.exists()` guards in
`_content_files` / `_managed_markdown_files` / `_build_workflows`; absent dirs
yield empty catalogs with no error. Full suite green.

- `flows/` absent → empty workflow catalog, no error.
- `capabilities/` absent → no scan error; XID resolution degrades cleanly.

Acceptance: missing `flows/` / `capabilities/` preserve current behavior with
empty catalogs; existing tests green.

### MCP-102 (Phase A): Surface triad / preconditions / knowledge_slots (superset)

Status: done — `SkillCatalogEntry` gained `capability` / `tuning` /
`responsibility` / `preconditions` / `knowledge_slots`; `_build_skill_entry`
parses them (`responsibility` from the new explicit field, not the opaque legacy
nested bullet); `_parse_knowledge_slots` tolerates absent/structured slots.
Regression test `test_surfaces_triad_preconditions_and_knowledge_slots` added.

- `_build_skill_entry` parses `capability` / `tuning` / `responsibility`,
  `preconditions`, `knowledge_slots` in addition to current fields.
- `SkillCatalogEntry` gains the fields; existing fields kept during transition.

Acceptance: new fields surfaced; old responses unchanged; tests green.

### MCP-103 (Phase A): Remove structure-graph client-dependency instruction (M7)

Status: done — replaced the "install NuGet `XRefKit.StructureGraph`" client-tool
instruction with the corrected model (analysis/build-side tool; client consumes
findings knowledge; Skill-scoped + prompt-supplemented if ever client-side).

- Remove the "install NuGet `XRefKit.StructureGraph`" line from
  `_client_tool_distribution` instructions and the client-run framing for
  structure-graph-consuming scripts.
- `structure_graph` stays kernel-code, opt-in and Skill-scoped.

Acceptance: distribution instructions no longer name `XRefKit.StructureGraph` as
a baseline dependency; any `structure_graph` need is Skill-declared.

### MCP-104 (Phase B): Knowledge slot resolution (M5)

Status: done — `XRefCatalog.resolve_skill_knowledge(skill_id)` resolves each
declared slot (query-ranked over base+local knowledge, or a pinned `bind` XID),
applies `domain` filter and `min`/`required` acceptance, and reports
`unsatisfied_required`. Exposed as the `resolve_skill_knowledge` MCP tool
(startup-gated, control-reminder). Compact slot spec parsing added
(`_parse_slot_spec`). Regression test `test_resolve_skill_knowledge_resolves_slots`.

- Add `resolve_skill_knowledge(skill_id)` or reuse `build_knowledge_context`
  per slot; return ranked candidates + acceptance metadata (`min`, `domain`,
  `required`) over the base+local unified catalog.

Acceptance: a Skill's required slots resolve to `>= min` candidates; local-pack
knowledge can satisfy a slot.

### MCP-105 (Phase B): Routing over triad + preconditions (M4)

Status: done — `rank_skills_for_purpose` scores `capability` / `tuning` /
`responsibility` facets (additive; empty for un-migrated skills) and reports
`declared_preconditions` in `execution_readiness`. Verified against the real
repo: `csharp_review` surfaces a `tuning=C#` facet. Regression test
`test_rank_skills_uses_triad_facets_and_reports_preconditions`.

- `rank_skills_for_purpose` scores against triad + `applies_when` +
  `preconditions`.
- Optional precondition-aware runnable readiness (mirrors the tool-availability
  `execution_readiness.runnable`).

Acceptance: ranking uses the triad; runnable filter reflects preconditions.

### MCP-106 (Phase C): Remove the workflow catalog (M1)

Status: pending

- Remove `list_workflows`, `_build_workflows`, `WorkflowCatalogEntry`,
  `flows/*.yaml` scanning, the `workflows` `semantic_routing_references` entry,
  and the `list_workflows` client obligation.

Acceptance: no workflow tool; `semantic_routing_references` has no `workflows`;
tests updated.
Depends on: XRefKit XK-004 (`flows/` removed).

### MCP-107 (Phase D): Remove capability + role handling (M2 / M3)

Status: pending

- Drop `capabilities` from the `_managed_markdown_files` scanned dirs; remove the
  `capability_refs` → `capabilities` derivation; drop `role_responsibilities`
  parsing.
- Optional: expose the capability/tuning/responsibility vocabulary registry.

Acceptance: `capabilities/` not scanned; `capability_refs` handling gone; role
parsing gone.
Depends on: XRefKit XK-003 (`capabilities/` dissolved), XK-002 (meta migrated).

### MCP-108 (Phase E): Revise the startup contract pack (M6)

Status: pending

- Rewrite the embedded `CANONICAL_STARTUP_CONTRACT_PACK_BODY` in
  `startup_contract_pack.py` to the 083 model; align with the revised 079 doc;
  regenerate `based_on` hashes.
- Update guard directionality wording (protocol/routing → Skill → External).

Acceptance: pack staleness check green; init wording matches 083; startup tests
updated.
Depends on: XRefKit XK-006 (079 revised) in step.

### MCP-109: Tests + CLI smoke

Status: pending

- Regression: empty `flows/`/`capabilities/`; triad surfaced; routing over
  triad; StructureGraph instruction absent; pack-revision hashes.

Acceptance: `pytest` green; CLI smoke commands succeed.

## Verification

```powershell
python -m pytest
python -m xrefkit_mcp.cli startup-context --repo C:\dev\itsm\XRefKit
python -m xrefkit_mcp.cli rank-skills --repo C:\dev\itsm\XRefKit --purpose "skill-centric routing"
```

## Open Items

- `resolve_skill_knowledge` as a new tool vs reuse `build_knowledge_context`.
- Vocabulary registry as compact startup metadata vs a dedicated tool.
