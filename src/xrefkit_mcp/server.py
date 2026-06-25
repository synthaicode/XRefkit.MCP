from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .catalog import XRefCatalog


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="xrefkit-mcp-server")
    parser.add_argument("--repo", required=True, help="Path to an XRefKit repository")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="MCP transport to serve. Use streamable-http for network clients.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host for HTTP transports")
    parser.add_argument("--port", type=int, default=8000, help="Port for HTTP transports")
    parser.add_argument(
        "--http-path",
        default="/mcp",
        help="Path for streamable-http transport",
    )
    args = parser.parse_args(argv)
    catalog = XRefCatalog.build(Path(args.repo))

    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise SystemExit(
            "The MCP server requires the optional dependency: "
            "python -m pip install -e .[mcp]"
        ) from exc

    app = FastMCP(
        "xrefkit-mcp",
        host=args.host,
        port=args.port,
        streamable_http_path=args.http_path,
    )

    @app.tool()
    def get_startup_context() -> dict[str, Any]:
        return catalog.get_startup_context()

    @app.tool()
    def list_knowledge_catalog(limit: int | None = None) -> list[dict[str, Any]]:
        return catalog.list_knowledge_catalog(limit)

    @app.tool()
    def search_knowledge_catalog(query: str, limit: int = 10) -> list[dict[str, Any]]:
        return catalog.search_knowledge_catalog(query, limit)

    @app.tool()
    def get_knowledge_summary(xid: str) -> dict[str, Any]:
        return catalog.expand_knowledge(xid)["entry"]

    @app.tool()
    def expand_knowledge(xid: str) -> dict[str, Any]:
        return catalog.expand_knowledge(xid)

    @app.tool()
    def get_document_by_xid(xid: str) -> dict[str, Any]:
        return catalog.get_document_by_xid(xid)

    @app.tool()
    def build_knowledge_context(query: str, limit: int = 5) -> dict[str, Any]:
        return catalog.build_knowledge_context(query, limit)

    @app.tool()
    def list_skills(limit: int | None = None) -> list[dict[str, Any]]:
        return catalog.list_skills(limit)

    @app.tool()
    def get_skill(skill_id: str) -> dict[str, Any]:
        return catalog.get_skill(skill_id)

    @app.tool()
    def list_workflows() -> list[dict[str, Any]]:
        return catalog.list_workflows()

    @app.tool()
    def get_skill_requirements(skill_id: str) -> dict[str, Any]:
        return catalog.get_skill_requirements(skill_id)

    @app.tool()
    def rank_skills_for_purpose(purpose: str, limit: int = 5) -> list[dict[str, Any]]:
        return catalog.rank_skills_for_purpose(purpose, limit)

    @app.tool()
    def list_tool_contracts() -> list[dict[str, Any]]:
        return catalog.list_tool_contracts()

    @app.tool()
    def get_client_tool_manifest() -> dict[str, Any]:
        return catalog.get_client_tool_manifest()

    @app.tool()
    def get_client_tool_file(path: str) -> dict[str, Any]:
        return catalog.get_client_tool_file(path)

    @app.tool()
    def get_client_tool_bundle() -> dict[str, Any]:
        return catalog.get_client_tool_bundle()

    @app.tool()
    def get_client_tool_pip_package() -> dict[str, Any]:
        return catalog.get_client_tool_pip_package()

    @app.tool()
    def check_client_tool_versions(installed: dict[str, str] | None = None) -> dict[str, Any]:
        return catalog.check_client_tool_versions(installed)

    app.run(transport=args.transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
