from __future__ import annotations

import unittest


class McpClientIntegrationTests(unittest.TestCase):
    def test_startup_and_skill_links_resolve_over_mcp(self) -> None:
        try:
            import anyio
            from mcp.client.session import ClientSession
            from mcp.client.stdio import StdioServerParameters, stdio_client
        except ImportError as exc:
            self.skipTest(f"mcp integration dependency is unavailable: {exc}")

        async def scenario() -> None:
            server = StdioServerParameters(
                command="python",
                args=[
                    "-m",
                    "xrefkit_mcp.server",
                    "--repo",
                    r"C:\dev\itsm\XRefKit",
                ],
                cwd=r"C:\dev\itsm\XRefkit.MCP",
            )
            async with stdio_client(server) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    startup_result = await session.call_tool("get_startup_context", {})
                    startup = startup_result.structuredContent
                    self.assertEqual(
                        startup["link_resolution"]["resolver_tool"],
                        "get_document_by_xid",
                    )
                    self.assertTrue(
                        any(
                            "get_document_by_xid" in instruction
                            for instruction in startup["client_instructions"]
                        )
                    )
                    uncertainty = next(
                        ref
                        for ref in startup["references"]
                        if ref["path"] == "docs/016_uncertainty_protocol.md"
                    )
                    self.assertIn("# Uncertainty Protocol", uncertainty["content"])
                    self.assertGreater(len(uncertainty["links"]), 0)
                    self.assertEqual(
                        uncertainty["links"][0]["resolver_tool"],
                        "get_document_by_xid",
                    )

                    startup_link_xid = uncertainty["links"][0]["xid"]
                    startup_doc_result = await session.call_tool(
                        "get_document_by_xid", {"xid": startup_link_xid}
                    )
                    startup_doc = startup_doc_result.structuredContent
                    self.assertEqual(startup_doc["xid"], startup_link_xid)
                    self.assertGreater(len(startup_doc["content"]), 1000)

                    skill_result = await session.call_tool(
                        "get_skill", {"skill_id": "csharp_review"}
                    )
                    skill = skill_result.structuredContent
                    self.assertEqual(skill["skill_id"], "csharp_review")
                    self.assertIn("# Skill: csharp_review", skill["skill_content"])
                    self.assertGreater(len(skill["skill_links"]), 0)
                    self.assertEqual(
                        skill["skill_links"][0]["resolver_tool"],
                        "get_document_by_xid",
                    )

                    skill_link_xid = skill["skill_links"][0]["xid"]
                    skill_doc_result = await session.call_tool(
                        "get_document_by_xid", {"xid": skill_link_xid}
                    )
                    skill_doc = skill_doc_result.structuredContent
                    self.assertEqual(skill_doc["xid"], skill_link_xid)
                    self.assertGreater(len(skill_doc["content"]), 1000)

                    manifest_result = await session.call_tool(
                        "get_client_tool_manifest", {}
                    )
                    manifest = manifest_result.structuredContent
                    self.assertEqual(manifest["execution_location"], "client")
                    self.assertEqual(manifest["version"], "0.1.0")
                    self.assertIs(manifest["server_executes_tools"], False)
                    self.assertTrue(
                        any(
                            file["path"] == "tools/cs_scope_probe.py"
                            for file in manifest["files"]
                        )
                    )

                    tool_file_result = await session.call_tool(
                        "get_client_tool_file",
                        {"path": "tools/cs_scope_probe.py"},
                    )
                    tool_file = tool_file_result.structuredContent
                    self.assertEqual(tool_file["kind"], "python")
                    self.assertIn("argparse", tool_file["imports"])
                    self.assertIn("def main", tool_file["content"])

                    package_result = await session.call_tool(
                        "get_client_tool_pip_package", {}
                    )
                    package = package_result.structuredContent
                    self.assertEqual(package["package_format"], "zip-sdist")
                    self.assertEqual(package["version"], "0.1.0")
                    self.assertIn("python -m pip install", package["install_command"])
                    self.assertGreater(len(package["content_base64"]), 1000)

                    version_result = await session.call_tool(
                        "check_client_tool_versions",
                        {
                            "installed": {
                                "xrefkit-client-python-tools": "0.1.0",
                                "xrefkit-client-tools": "0.1.0",
                            }
                        },
                    )
                    self.assertIs(version_result.structuredContent["ok"], True)

        anyio.run(scenario)


if __name__ == "__main__":
    unittest.main()
