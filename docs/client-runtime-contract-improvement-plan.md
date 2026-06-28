# Client Runtime Contract Improvement Plan

## Purpose

This plan records improvements for making XRefKit MCP easier for AI clients to
consume as a governance content plane.

The server boundary is intentionally read-only:

- XRefKit MCP distributes startup context, XID documents, Skill content,
  workflow metadata, tool contracts, and client-side Python tools.
- AI reasoning, repository mutation, external IO, approval, closure, sandboxing,
  and observability remain on the client side or in the client's execution
  environment.
- Server-side MCP tools must keep `side_effects: none`.

The improvement target is therefore not to move execution into the MCP server.
The target is to make the client-side obligations explicit, machine-readable,
and testable.

## Client Tool Assumption

The intended client model is not "the client already has the XRefKit repository
checkout and runs local tools from it."

The intended model is:

1. The client connects to XRefKit MCP.
2. The client receives the client-tool manifest during startup.
3. The client checks installed client-tool versions.
4. If missing or stale, the client fetches tool files, a bundle, or the
   pip-installable package from XRefKit MCP.
5. The client materializes or installs those tools in its own execution
   environment.
6. The client runs those tools locally, against the client-side target
   repository or supplied artifacts.

XRefKit MCP is therefore the distribution source for XRefKit client tools. The
server still does not execute those tools.

## Current Confirmed Behavior

Local verification was performed against:

```text
http://127.0.0.1:8001/mcp
```

Confirmed MCP tools include:

- `get_repository_identity`
- `get_startup_context`
- `get_document_by_xid`
- `list_skills`
- `get_skill`
- `get_skill_requirements`
- `list_workflows`
- `list_tool_contracts`
- `get_client_tool_manifest`
- `get_client_tool_file`
- `get_client_tool_bundle`
- `get_client_tool_pip_package`
- `check_client_tool_versions`

Confirmed startup behavior:

- `access_policy.mode` is `mcp_only`.
- `access_policy.source_of_truth` is `xrefkit_mcp`.
- XID links resolve through `get_document_by_xid`.
- Startup references include content and link metadata.
- Client-side Python tool distribution is exposed by manifest and bundle APIs.
- Startup includes `client_tool_distribution`, so a client can discover the
  expected tool package and file set without a local XRefKit checkout.

Confirmed contract boundary:

- `ToolContract` declares `execution_location` and `side_effects`.
- Server-side tools validate that `side_effects` is `none`.
- Client tools are distributed for client-side execution; the server does not
  execute them.

## Improvement Goals

1. Make client obligations machine-readable. **Implemented**
2. Make API response envelopes predictable for client implementers. **Implemented through ToolContract metadata**
3. Make tool contract schemas strict enough for validation and SDK generation. **Implemented through JSON Schema-compatible contract fields**
4. Make client-side tool installation and version enforcement auditable. **Implemented through distribution metadata**
5. Provide conformance tests that prove a client can follow the startup and
   XID-resolution contract.

## Work Plan

### 1. Machine-Readable Client Obligations

Add a structured `client_obligations` block to `get_startup_context`.
Status: implemented.

Candidate shape:

```json
{
  "client_obligations": [
    {
      "id": "startup.first_call",
      "level": "must",
      "applies_when": "xrefkit_mcp_configured",
      "statement": "Call get_startup_context before task-specific routing.",
      "enforcement_owner": "client"
    },
    {
      "id": "content.mcp_only",
      "level": "must",
      "applies_when": "access_policy.mode == mcp_only",
      "statement": "Do not read XRefKit governance Markdown from local filesystem.",
      "enforcement_owner": "client"
    }
  ]
}
```

This should complement, not replace, the existing human-readable
`client_instructions`.

### 2. Strict Tool Contract Schemas

Upgrade `ToolContract.input_schema` and `ToolContract.output_schema` from light
descriptors such as `"string"` and `"object?"` to JSON Schema-compatible
objects.
Status: implemented by adding `input_json_schema` and `output_json_schema` while
keeping the compact fields for compatibility.

Keep the current compact descriptors only if they remain useful as a display
summary.

Target benefits:

- client-side validation
- generated client bindings
- clearer compatibility checks
- fewer client-specific assumptions about optional fields

### 3. Response Envelope Consistency

Document or normalize list-style responses.
Status: implemented by adding `response_envelope` metadata to ToolContract and
documenting the current MCP result wrapper behavior.

Observed behavior:

- Object-returning tools expose their fields directly in `structuredContent`.
- List-returning tools are wrapped as `structuredContent.result` by the MCP
  layer.

Options:

- Keep the current behavior and document it in README and tool contracts.
- Or change list-returning server functions to return named objects such as
  `{ "skills": [...] }`, `{ "contracts": [...] }`, and `{ "workflows": [...] }`.

Preferred direction: return named objects for new or versioned APIs, while
preserving current tools until a compatibility plan exists.

### 4. Client Tool Version Enforcement

Make client-side tool distribution enforcement more explicit.
Status: implemented by adding manifest metadata for required packages, versions,
hash algorithm, materialization tools, and update policy.

This assumes client tools are sourced from MCP distribution APIs, not from an
already-present local XRefKit checkout. A local checkout may be used for
development, but it is not the portable client contract.

Add fields to `get_client_tool_manifest` or a related contract:

- required package ids
- current package versions
- expected installation layout
- file hash algorithm
- minimum compatible client contract version
- update required / update recommended status

Add a client-facing checklist:

1. call `get_client_tool_manifest`
2. call `check_client_tool_versions`
3. fetch `get_client_tool_bundle`, `get_client_tool_file`, or
   `get_client_tool_pip_package` when installation or update is required
4. materialize files or install the package in the client execution environment
5. verify installed hashes or package version
6. execute tools only on the client side

### 5. Startup Conformance Test

Add a small client conformance test that verifies:
Status: partially implemented in catalog and MCP integration tests; a standalone
published client checklist can still be added later.

- the client calls `get_startup_context`
- `access_policy.mode` is honored
- startup references are processed in `load_order`
- at least one startup link is resolved through `get_document_by_xid`
- `known_version` returns `not_modified` when the cached content hash matches
- `list_skills(include_content=false)` can be used without loading Skill bodies
- `get_skill` can provide Skill content and XID links on demand

This can start as a Python smoke test under `tests/` and later become a
published client checklist.

### 6. Explicit Runtime Boundary Document

Create or expand documentation that states which responsibilities belong to each
side:

| Responsibility | XRefKit MCP server | AI client / runtime |
|---|---|---|
| Startup governance content | provides | consumes and applies |
| XID resolution | provides | calls through MCP |
| Skill procedure body | provides | executes client-side |
| Python tools | distributes manifest/files/package | materializes, installs, verifies, and runs |
| Repository mutation | no | yes, if authorized |
| External API calls | no | yes, if authorized |
| Sandbox and permissions | no | yes |
| Observability and traces | no | yes |
| Closure and handoff | provides contract | executes and records |

This prevents future confusion between a content-plane MCP server and a
server-side agent runtime.

## Proposed Priority

1. Document response envelope behavior.
2. Add `client_obligations` to startup response.
3. Add startup conformance test.
4. Expand client tool version enforcement metadata.
5. Convert tool contracts to JSON Schema-compatible form.

## Non-Goals

- Do not add server-side Skill execution.
- Do not add repository mutation APIs to the MCP server.
- Do not make XRefKit MCP a generic Git or shell execution service.
- Do not move client sandbox, approval, or external IO policy into the server.
- Do not use local filesystem access as a substitute for MCP-only mode.

## Open Questions

- Should `client_obligations` be versioned independently from
  `catalog_version`?
- Should existing list-returning APIs be changed, or should named-object
  responses be introduced only in versioned replacements?
- Should the client-side tool package expose its own self-check command?
- Should `ToolContract` include a compatibility range for client harness
  versions?
- Should conformance failures be expressed as a structured report that AI
  clients can include in startup diagnostics?
