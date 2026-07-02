# 2026-07-03 Session: Plain-HTTP artifact distribution (/dist) and stdlib bootstrap

## Event

Reviewed XRefKit / XRefKit.MCP against the "MCP as context distribution"
article and implemented the accepted remediation: separate the artifact
channel from the context channel.

- Added `/dist` plain-HTTP routes on the streamable-http transport
  (`src/xrefkit_mcp/dist.py`): `index.json` manifest with sha256, pip
  `--find-links` HTML index, per-artifact download, operator-mirrored extra
  files via `--dist-extra-dir`.
- Added stdlib-only `bootstrap.py` (served at `/dist/bootstrap.py`): no
  pip/PyPI/`mcp` package needed; verifies sha256, materializes `fm/` and
  `tools/` or pip-installs offline; optional minimal MCP JSON-RPC handshake
  saves `get_startup_context` first.
- When distribution is active, `get_*_pip_package` return `download_url` +
  `content_hash` instead of base64; `get_startup_context` gains
  `artifact_distribution`; manifests/bundles gain `http_distribution`.
- Made generated package zips byte-deterministic (fixed zip timestamps) so
  previously handed-out sha256 values match later downloads.
- New CLI options: `--public-base-url`, `--dist-extra-dir`.

Verification: 65 tests pass (new `tests/test_dist.py`); end-to-end smoke on
127.0.0.1:8765 against C:\dev\itsm\XRefKit — bootstrap downloaded, verified,
materialized 13 fm files + 22 tools files, `python -m fm --help` ran in the
materialized client repo.

Follow-up event (same day): added
`docs/guides/078_structure_graph_build_guide.md` (xid 8B3E5D0A94C7) to the
XRefKit repository — build procedure for the C# `tools/structure_graph`
binary required after any source-level copy (bin/ is gitignored). Indexed
in docs/000_index.md and tools/README.md; XRefKit.MCP distribution warnings
now point to it by path and XID. Build verified with .NET SDK 10 (Release,
0 errors; NU1903 documented as expected).

Follow-up event (same day, later): packaged tools/structure_graph as the
NuGet dotnet tool XRefKit.StructureGraph (command dotnet-xrefkit-graph) in
the XRefKit repository (monorepo publishing decided; no separate repo).
Added two workflows mirroring Ksql.Linq.Cli's release flow:
structure-graph-nuget-publish.yml (tag structure-graph-vX.Y.Z → nuget.org,
with a package-major ↔ schema-major consistency gate against
xrefkit.structure_graph/v<N> in Program.cs) and
structure-graph-publish-github-packages.yml (rc tags / dispatch → GitHub
Packages). Verified locally: dotnet pack 0.1.0 → tool-path install from
local artifact → no-arg smoke (usage on stderr, exit 2 — guide 078
corrected; earlier "exit 0" claim was a measurement error). Guide 078
restructured: Option A NuGet install (preferred, incl. /dist-mirrored
nupkg for closed networks), Option B build from source, maintainer
publishing section. MCP distribution warnings now name the package.

## Decision

Human accepted the proposal: MCP channel = governance context only; plain
HTTP on the same server = executable artifacts; stdlib bootstrap replaces
the `pip install mcp` prerequisite.

## Human Stated Reason

Client-side AI is assumed to have a Python execution environment; package
bytes must not consume model context; clients may reach only the MCP server
(no PyPI), so the same server must relay what clients need.

## Deferred

- Startup contract pack drift detection (`based_on_hashes` or moving the
  pack body into the XRefKit repo).
- `expand_knowledge` freshness fix (frozen `content_hash` with live content).
- `list_skills` default `include_content=False` and gating alignment.
- Authentication in front of `/dist` (currently TLS + reverse proxy
  guidance only, documented in README Security Notes).

## Open

- Whether XRefKit-side docs (077 initialization sequence) should describe
  the bootstrap path for network clients without a local checkout.
