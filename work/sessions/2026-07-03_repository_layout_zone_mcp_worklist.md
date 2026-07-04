# Repository layout zone MCP worklist

## Scope

This worklist tracks XRefKit.MCP changes needed to serve the repository layout
zone model and pack-centric catalog discovery.

Related XRefKit documents:

- `docs/designs/080_repository_layout_zones_design.md`
- `docs/designs/081_repository_layout_mcp_catalog_design.md`

Branch:

- `codex/repository-layout-zones-mcp`

## Work Items

### MCP-001: Read and normalize `ownership.yaml`

Status: done

Add MCP-side ownership loading for the served XRefKit repository.

Acceptance:

- missing `ownership.yaml` falls back to current fixed-root behavior
- present `ownership.yaml` is parsed into a normalized zone model
- invalid paths outside the served repository fail validation
- normalized model hash is available for catalog and startup metadata

### MCP-002: Make catalog scanners multi-root

Status: done

Update Skill, knowledge, workflow, and capability scanners to include pack roots.

Acceptance:

- scans root-level content and `packs/*` content
- handles `packs/local/*` as local-only when enabled by the zone model
- preserves existing tool names and response compatibility
- generated and record zones are not included in normal catalogs

### MCP-003: Add zone metadata to catalog entries

Status: done

Attach zone and pack metadata to catalog responses without forcing clients to
load bodies.

Acceptance:

- entries include path, content hash, zone, owner, pack id when applicable,
  locality, and distribution eligibility
- `content_hash` remains the version identity
- metadata-only `list_skills` stays lightweight

### MCP-004: Implement shadow/fork/conflict classification

Status: done

Classify duplicate stable identities across base roots, shared packs, and local
packs.

Acceptance:

- Skill conflicts are keyed by `skill_id`
- Markdown conflicts are keyed by XID
- explicit `forked_from` relations are reported as forks instead of silent
  conflicts
- unresolved duplicate identities fail closed where body resolution would be
  ambiguous

### MCP-005: Update `get_document_by_xid`

Status: done

Resolve XIDs across all catalog-eligible roots with explicit conflict handling.

Acceptance:

- unique XID returns normally
- forked local or pack document reports the selected document and base metadata
- duplicate XID without provenance returns a conflict response
- no path-order fallback decides ambiguous content

### MCP-006: Update selected-Skill client-tool distribution

Status: done

Include pack Skill scripts in client-tool file or bundle distribution only after
Skill selection.

Acceptance:

- root `skills/**/*.py` behavior remains unchanged
- `packs/*/skills/**/*.py` follows selected-Skill distribution
- `packs/local/*/skills/**/*.py` is local-only and not public/base
  distributable
- startup does not download optional Skill tool files

### MCP-007: Add compact startup metadata

Status: done

Expose zone state in `get_startup_context` without expanding pack catalogs.

Acceptance:

- reports whether ownership metadata was found
- includes normalized ownership hash
- reports enabled root families and local-pack presence
- does not inject pack bodies or full catalogs into startup

### MCP-008: Add tests and CLI smoke coverage

Status: done

Add regression coverage for the zone-aware catalog model.

Acceptance:

- missing ownership file preserves current behavior
- pack roots appear in list/search/ranking tools
- local-only roots are excluded from public distribution outputs
- duplicate XID/skill conflicts are deterministic
- startup metadata stays compact

Progress:

- Added ownership loader tests.
- Added catalog tests for missing ownership fallback, pack-root discovery, zone
  metadata, and compact startup zone metadata.
- Added duplicate XID and duplicate skill_id conflict tests.
- Added selected-Skill/client-tool bundle coverage for pack Skill scripts and
  local-only exclusion.
- Added rank-skills-specific pack-root coverage.

## Verification

Run before closing this worklist:

```powershell
python -m pytest
xrefkit-mcp-catalog startup-context --repo C:\dev\itsm\XRefKit
xrefkit-mcp-catalog list-workflows --repo C:\dev\itsm\XRefKit
xrefkit-mcp-catalog rank-skills --repo C:\dev\itsm\XRefKit --purpose "repository layout zone migration"
```

If a command requires package installation or an active editable environment,
record the exact environment setup used.

Completed:

```powershell
python -m pytest
python -m xrefkit_mcp.cli startup-context --repo C:\dev\itsm\XRefKit
python -m xrefkit_mcp.cli list-workflows --repo C:\dev\itsm\XRefKit
python -m xrefkit_mcp.cli rank-skills --repo C:\dev\itsm\XRefKit --purpose "repository layout zone migration"
```

## Open Items

- Decided: keep `get_repository_zones` internal for this implementation. Zone
  state is exposed through compact `get_startup_context.repository_zones`
  metadata until a client needs a dedicated public tool.
- Decided: local pack discovery is enabled by default when `ownership.yaml`
  declares `packs/local/` with `catalog: true`; local pack tool scripts remain
  non-distributable when the zone has `distribution: false`.
- Decided: duplicate-identity conflict responses are the explicit fail-closed
  schema already implemented for XID bodies: `{ok:false, error:"xid_conflict",
  xid, message, matches:[{path, content_hash, zone_metadata}]}`. Duplicate
  Skill IDs are reported in `list_skills[].zone_metadata.identity_conflict`
  and `get_skill` fails closed with `ValueError` until a formal public error
  envelope is needed.
