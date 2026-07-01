## Personal Codex instruction

This user works with XRefKit-style repository governance.

At session start, follow the repository-defined loading process and treat loaded AGENTS.md, Skills, knowledge, workflow definitions, and governance labels as authoritative.

Do not redefine XRefKit concepts such as unknown, risk, judgment, escalation, evidence, handoff, or skill routing in global custom instructions. Use the repository definitions.

Global instructions should only control:
- concise communication
- progress visibility
- explicit summary of changes
- explicit list of unverified items
- respect for repository-defined stop-and-escalate rules

If a required rule is missing, do not invent a project rule. Mark it as missing and suggest whether it belongs in AGENTS.md, a Skill, knowledge, or workflow definition.

--- project-doc ---

# AGENTS Startup (XRefKit MCP)

**As your first action**, read the MCP startup contract below:

- `README.md#ai-client-instruction-template`
- `README.md#required-client-startup-flow`

When working against an XRefKit repository through this MCP server, call `get_startup_context` first and resolve XID-linked documents with `get_document_by_xid`.
