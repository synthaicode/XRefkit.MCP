from __future__ import annotations

import argparse
import json
from pathlib import Path

from .catalog import XRefCatalog


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="xrefkit-mcp-catalog")
    sub = parser.add_subparsers(dest="command", required=True)

    catalog = sub.add_parser("catalog", help="build and print catalog summary")
    catalog.add_argument("--repo", required=True)

    identity = sub.add_parser(
        "repository-identity",
        help="print the repository cache identity",
    )
    identity.add_argument("--repo", required=True)

    startup = sub.add_parser("startup-context", help="print required startup references")
    startup.add_argument("--repo", required=True)

    knowledge = sub.add_parser("search-knowledge", help="search knowledge catalog")
    knowledge.add_argument("--repo", required=True)
    knowledge.add_argument("--query", required=True)
    knowledge.add_argument("--limit", type=int, default=10)

    expand = sub.add_parser("expand-knowledge", help="expand one knowledge body")
    expand.add_argument("--repo", required=True)
    expand.add_argument("--xid", required=True)

    document = sub.add_parser("get-document", help="expand any managed Markdown document by XID")
    document.add_argument("--repo", required=True)
    document.add_argument("--xid", required=True)
    document.add_argument("--known-version")

    context = sub.add_parser("build-knowledge-context", help="expand bounded knowledge context")
    context.add_argument("--repo", required=True)
    context.add_argument("--query", required=True)
    context.add_argument("--limit", type=int, default=5)

    skills = sub.add_parser("list-skills", help="list Skill catalog")
    skills.add_argument("--repo", required=True)
    skills.add_argument("--limit", type=int)
    skills.add_argument("--exclude-content", action="store_true")

    skill = sub.add_parser("get-skill", help="get one Skill catalog entry with transferred content")
    skill.add_argument("--repo", required=True)
    skill.add_argument("--skill-id", required=True)

    workflows = sub.add_parser("list-workflows", help="list workflow catalog")
    workflows.add_argument("--repo", required=True)

    rank = sub.add_parser("rank-skills", help="rank Skill candidates for a purpose")
    rank.add_argument("--repo", required=True)
    rank.add_argument("--purpose", required=True)
    rank.add_argument("--limit", type=int, default=5)

    contracts = sub.add_parser("tool-contracts", help="list read-only tool contracts")
    contracts.add_argument("--repo", required=True)

    tool_manifest = sub.add_parser("client-tool-manifest", help="list distributable client-side tool files")
    tool_manifest.add_argument("--repo", required=True)

    tool_file = sub.add_parser("get-client-tool-file", help="get one distributable client-side tool file")
    tool_file.add_argument("--repo", required=True)
    tool_file.add_argument("--path", required=True)

    tool_bundle = sub.add_parser("client-tool-bundle", help="get all distributable client-side tool files")
    tool_bundle.add_argument("--repo", required=True)

    tool_package = sub.add_parser("client-tool-pip-package", help="get a pip-installable client tool package")
    tool_package.add_argument("--repo", required=True)

    version_check = sub.add_parser("check-client-tool-versions", help="check installed client tool versions")
    version_check.add_argument("--repo", required=True)
    version_check.add_argument(
        "--installed",
        action="append",
        default=[],
        help="Installed package version as package_id=version. Can be repeated.",
    )

    args = parser.parse_args(argv)
    model = XRefCatalog.build(Path(args.repo))

    if args.command == "catalog":
        payload = {
            "catalog_version": model.catalog_version,
            "knowledge_count": len(model.knowledge),
            "skill_count": len(model.skills),
            "tool_contract_count": len(model.tools),
        }
    elif args.command == "repository-identity":
        payload = model.get_repository_identity()
    elif args.command == "startup-context":
        payload = model.get_startup_context()
    elif args.command == "search-knowledge":
        payload = model.search_knowledge_catalog(args.query, args.limit)
    elif args.command == "expand-knowledge":
        payload = model.expand_knowledge(args.xid)
    elif args.command == "get-document":
        payload = model.get_document_by_xid(args.xid, args.known_version)
    elif args.command == "build-knowledge-context":
        payload = model.build_knowledge_context(args.query, args.limit)
    elif args.command == "list-skills":
        payload = model.list_skills(args.limit, not args.exclude_content)
    elif args.command == "get-skill":
        payload = model.get_skill(args.skill_id)
    elif args.command == "list-workflows":
        payload = model.list_workflows()
    elif args.command == "rank-skills":
        payload = model.rank_skills_for_purpose(args.purpose, args.limit)
    elif args.command == "tool-contracts":
        payload = model.list_tool_contracts()
    elif args.command == "client-tool-manifest":
        payload = model.get_client_tool_manifest()
    elif args.command == "get-client-tool-file":
        payload = model.get_client_tool_file(args.path)
    elif args.command == "client-tool-bundle":
        payload = model.get_client_tool_bundle()
    elif args.command == "client-tool-pip-package":
        payload = model.get_client_tool_pip_package()
    elif args.command == "check-client-tool-versions":
        installed = dict(item.split("=", 1) for item in args.installed)
        payload = model.check_client_tool_versions(installed)
    else:
        parser.error(f"unknown command: {args.command}")

    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
