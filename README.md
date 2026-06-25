# XRefKit MCP

Read-only MCP projection layer for XRefKit repositories.

The server sends inactive definitions only:

- startup/base-control Markdown content
- workflow catalog entries from `flows/**/*.yaml`
- knowledge catalog entries from `knowledge/**/*.md`
- Skill metadata and `SKILL.md` content from `skills/**`
- distributable Python tool files from `tools/**/*.py` for client-side execution
- read-only tool contracts for catalog, expansion, and routing tools

It does not execute Skills, mutate repositories, approve knowledge updates, or
run arbitrary Git commands.

## Install

```powershell
cd C:\dev\itsm\XRefkit.MCP
python -m pip install -e ".[mcp]"
```

## Run A Network Server

Use `streamable-http` for clients connecting over the network.

```powershell
xrefkit-mcp-server `
  --repo C:\dev\itsm\XRefKit `
  --transport streamable-http `
  --host 0.0.0.0 `
  --port 8000
```

The client URL is:

```text
http://<server-host>:8000/mcp
```

For local-only testing, bind to loopback:

```powershell
xrefkit-mcp-server --repo C:\dev\itsm\XRefKit --transport streamable-http --host 127.0.0.1 --port 8000
```

`stdio` is still available for local clients:

```powershell
xrefkit-mcp-server --repo C:\dev\itsm\XRefKit
```

## Client Configuration

Client configuration syntax differs by MCP client, but the required values are:

```json
{
  "name": "xrefkit",
  "transport": "streamable-http",
  "url": "http://<server-host>:8000/mcp"
}
```

If a client uses an `mcpServers` map, the equivalent shape is:

```json
{
  "mcpServers": {
    "xrefkit": {
      "transport": "streamable-http",
      "url": "http://<server-host>:8000/mcp"
    }
  }
}
```

If your MCP client only supports stdio, run the server locally with stdio or use
that client's supported remote-MCP bridge. The XRefKit MCP endpoint itself is
the Streamable HTTP URL above.

## Required Client Startup Flow

The client should call `get_startup_context` first.

That response contains:

- `client_instructions`
- `link_resolution`
- base-control Markdown references, including full `content`
- workflow catalog entries
- executor/checker runtime role contract

The client must not assume the XRefKit repository exists on the client machine.
Use the transferred Markdown content and resolve any needed XID links through
MCP.

Link resolution rule:

```json
{
  "link_field": "links",
  "xid_field": "xid",
  "resolver_tool": "get_document_by_xid",
  "resolver_argument": "xid",
  "example_call": "get_document_by_xid({\"xid\": \"8A666C1FD121\"})"
}
```

Every transferred Markdown link entry also repeats the resolver fields:

```json
{
  "xid": "5A1C8E4D2F90",
  "target": "017_base_and_xref_layering.md#xid-5A1C8E4D2F90",
  "path": "017_base_and_xref_layering.md",
  "resolver_tool": "get_document_by_xid",
  "resolver_argument": "xid"
}
```

To inspect a Skill when the client has no local Skill files, call `get_skill`.
The response includes:

- `meta_content`
- `meta_links`
- `skill_content`
- `skill_links`

Resolve `meta_links[]` and `skill_links[]` the same way: call
`get_document_by_xid` with the link `xid`.

## Client-Side Python Tools

Python code under XRefKit `tools/` is distributed for client-side execution. The
server never runs these tools.

Startup includes `client_tool_distribution`, a manifest with file paths, hashes,
run hints, package version, and resolver information. During client
initialization, call `check_client_tool_versions` with the installed package
versions and install/update the client tools when the check fails.

Example version check:

```json
{
  "installed": {
    "xrefkit-client-python-tools": "0.1.0",
    "xrefkit-client-tools": "0.1.0"
  }
}
```

To install the tools on a client that does not have the XRefKit checkout:

1. Call `get_client_tool_manifest` to inspect available files.
2. Call `get_client_tool_bundle` to fetch all distributable files, or
   `get_client_tool_file({"path": "tools/cs_scope_probe.py"})` for one file.
3. Write each returned file to the same relative path under the client-side
   target repository root.
4. Run tools on the client side, for example `python tools/cs_scope_probe.py`.

Alternatively, fetch a pip-installable source package with
`get_client_tool_pip_package`. The response contains `filename`,
`install_command`, `content_base64`, `content_hash`, and `warnings`. Write
`content_base64` to `filename`, then install it:

```powershell
python -m pip install xrefkit-client-tools-0.1.0.zip
```

The package preserves the top-level `tools` package because some scripts import
siblings such as `tools.error_policy_locator`. Install it in a project virtual
environment to avoid conflicts with unrelated packages named `tools`.

The distribution currently includes:

- `tools/**/*.py`
- support files under `tools/profiles/`
- `tools/README.md`

The C# `tools/structure_graph/` project is not bundled by the Python tool
distribution. Python tools that consume `structure_graph` output still expect
that output to be produced separately on the client side.

## Useful CLI Checks

```powershell
xrefkit-mcp-catalog startup-context --repo C:\dev\itsm\XRefKit
xrefkit-mcp-catalog list-workflows --repo C:\dev\itsm\XRefKit
xrefkit-mcp-catalog get-document --repo C:\dev\itsm\XRefKit --xid 8A666C1FD121
xrefkit-mcp-catalog get-skill --repo C:\dev\itsm\XRefKit --skill-id csharp_review
xrefkit-mcp-catalog client-tool-manifest --repo C:\dev\itsm\XRefKit
xrefkit-mcp-catalog get-client-tool-file --repo C:\dev\itsm\XRefKit --path tools/cs_scope_probe.py
xrefkit-mcp-catalog client-tool-bundle --repo C:\dev\itsm\XRefKit
xrefkit-mcp-catalog client-tool-pip-package --repo C:\dev\itsm\XRefKit
xrefkit-mcp-catalog check-client-tool-versions --repo C:\dev\itsm\XRefKit --installed xrefkit-client-python-tools=0.1.0 --installed xrefkit-client-tools=0.1.0
xrefkit-mcp-catalog rank-skills --repo C:\dev\itsm\XRefKit --purpose "review C# code for non-Roslyn risks"
```

## Python Client Smoke Test

```python
import anyio
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main():
    async with streamablehttp_client("http://127.0.0.1:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            startup = await session.call_tool("get_startup_context", {})
            context = startup.structuredContent

            first_link = context["references"][0]["links"][0]
            document = await session.call_tool(
                first_link["resolver_tool"],
                {first_link["resolver_argument"]: first_link["xid"]},
            )
            print(document.structuredContent["title"])


anyio.run(main)
```

## Security Notes

This server is read-only, but it can expose repository documentation and Skill
content over the network. Bind to `127.0.0.1` unless the network is trusted or a
reverse proxy / gateway provides authentication and transport security.

Do not expose `0.0.0.0:8000` directly to an untrusted network.

## Boundary

This package intentionally keeps the server plane read-only. Tool contracts
declare `execution_location` and `side_effects`; server-side tools are rejected
at definition time unless `side_effects` is `none`.
