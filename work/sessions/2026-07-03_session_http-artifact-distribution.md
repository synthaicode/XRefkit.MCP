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

Follow-up event (same day, later still): fixed the repository_fingerprint
identity problem. Fingerprint is now derived from the git root commit(s)
of HEAD's history (fingerprint_basis git_root_commits, scope
shared_across_clones) so all full clones share one cache namespace across
paths and machines; non-git directories, commitless repositories, and
shallow clones fall back to the old resolved-path basis (scope
local_path_only), and get_repository_identity reports basis and scope
honestly. Cache safety is unchanged (content_hash still validates every
entry); upgrading servers start one fresh namespace (old cache dirs
orphaned, not corrupted). 8 new tests incl. clone-shares-fingerprint and
shallow-clone fallback; 73 total pass.

Follow-up event (same day, freshness fix): unified the catalog freshness
model. knowledge, skills, and catalog_version are now properties rebuilt
from the live repository on every access (one read per file, so entry
content_hash and body can never disagree — this removes the
expand_knowledge stale-hash bug), matching get_document_by_xid's live
reads. Files added/removed after server start now appear/disappear
without a restart; the frozen build-time snapshot and _fresh_skill_entry
are gone. Regression tests added (FreshnessTests in test_catalog.py).

Incident during the fix: moving knowledge scans into request handlers made
every knowledge tool spawn `git log` per file (revised_at), and a git
subprocess spawned inside a request handler hangs the stdio transport on
Windows — the tool completes but the response never reaches the client
(diagnosed by bisection: list_skills [no subprocess] responded in 0.1s,
search_knowledge_catalog [git spawns] timed out; the direct in-process
call took 2.5s). Resolution: no subprocess in any request path —
revised_at now comes from the file's mtime on the serving checkout
(repository.file_last_modified), git_last_modified was removed, and
repository_identity's git calls remain build-time only. get_startup_context
went from 2.5s (cold) to 0.2s as a side effect. 78 tests pass in ~11s.

Follow-up event (same day, list_skills gating): list_skills now defaults
to include_content=False (metadata-only, with document_versions for cache
negotiation), and include_content=true requires get_startup_context first
(XREFKIT_STARTUP_REQUIRED otherwise), closing the hole where one ungated
call returned every SKILL.md body before startup. Metadata-only routing
tools stay ungated by design. Tool contract xref.list_skills bumped to v3;
CLI flag flipped from --exclude-content to --include-content; obligation
verification text and README updated; catalog + integration tests added
(80 total pass).

Follow-up event (same day, pack drift detection): the startup contract
pack can no longer drift silently. Canonical pack body moved to the
XRefKit repository (docs/core/contracts/079_startup_contract_pack.md, xid
D4E8A1C63B57) so pack and sources are authored/reviewed in the same
commit; the doc declares based_on_hashes (source hashes at authoring
time). The server serves that doc when present (pack_source
repository_document) or the embedded body as fallback (embedded_fallback,
now also carrying based_on hashes), and on every get_startup_context
compares based_on_hashes with live source_hashes: mismatches set
stale/stale_sources and append a client instruction to prefer live
sources by XID and escalate. New CLI: startup-pack-hashes (regenerate
hash lines) and check-startup-pack (CI gate, exit 1 when stale). Real
repo verified stale=false; 84 tests pass (4 new drift tests).

Follow-up event (same day, base-sync handoff package): built
handoff/base_sync/ in the XRefKit repo for the base-vs-local divergence
problem. export_base_manifest.py (base side, git) freezes the
codex/sync-main-without-mp4-action history into a portable 546KB manifest
(XID -> path/xid-normalized hash/anchors, delta-encoded per commit).
xrefkit_sync_worklist.py (local side, stdlib-only, read-only)
content-dates the local file copy against the manifest and produces an
XID-keyed 3-way worklist (base@copy/base@head/local) for the absorbing AI.
HANDOFF.md is the Sonnet-facing prompt encoding the agreed policy: adopt
base-only changes, ladder-classify local-only changes (facts->knowledge,
params->bindings, procedure->fork with fork_base_hash), intake no-XID
files as new with new XIDs and let the local AI repoint Skill references,
never auto-merge both_changed. Verified on a synthetic fixture (40-commits
-old snapshot + injected mutations): copy point identified exactly (99%
match), all injected mutations classified 1:1, and the real base docs/
reorganization tracked as 25 moved_in_base instead of false conflicts.
Two design lessons captured in code: XID identity must come from
declarations only (link references and words like "xid-based" poisoned
first_xid), and human-docs/ translations legitimately reuse canonical XIDs
so they are path-keyed.

## Decision

Human accepted the proposal: MCP channel = governance context only; plain
HTTP on the same server = executable artifacts; stdlib bootstrap replaces
the `pip install mcp` prerequisite.

## Human Stated Reason

Client-side AI is assumed to have a Python execution environment; package
bytes must not consume model context; clients may reach only the MCP server
(no PyPI), so the same server must relay what clients need.

## Deferred

- (Closed by decision, same day: built-in authentication for /mcp and
  /dist will NOT be implemented. Human decision: this server is not
  universal — it supplies domain knowledge for very local use, so the
  security boundary is delegated to operations (network placement,
  reverse proxy when needed). README Security Notes now state this scope
  explicitly.)
- (Resolved later the same day: expand_knowledge freshness fix,
  list_skills default/gating, and startup-pack drift detection — see
  follow-up events above.)

## Open

- Whether XRefKit-side docs (077 initialization sequence) should describe
  the bootstrap path for network clients without a local checkout.
