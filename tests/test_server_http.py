from __future__ import annotations

import unittest

from xrefkit_mcp.server import (
    SERVER_VERSION,
    _endpoint_info,
    _should_return_endpoint_info,
)


class StreamableHttpProbeTests(unittest.TestCase):
    def test_plain_get_to_mcp_endpoint_returns_endpoint_info(self) -> None:
        self.assertTrue(
            _should_return_endpoint_info(
                "GET",
                "/mcp",
                {"accept": "text/html,*/*"},
                "/mcp",
            )
        )

    def test_streamable_http_get_stays_with_mcp_transport(self) -> None:
        self.assertFalse(
            _should_return_endpoint_info(
                "GET",
                "/mcp",
                {"accept": "application/json, text/event-stream"},
                "/mcp",
            )
        )

    def test_post_stays_with_mcp_transport(self) -> None:
        self.assertFalse(
            _should_return_endpoint_info(
                "POST",
                "/mcp",
                {"accept": "application/json"},
                "/mcp",
            )
        )

    def test_endpoint_info_is_actionable_for_browser_probe(self) -> None:
        info = _endpoint_info("/mcp")

        self.assertEqual(info["server"], "xrefkit-mcp")
        self.assertEqual(info["version"], SERVER_VERSION)
        self.assertEqual(info["transport"], "streamable-http")
        self.assertEqual(info["endpoint"], "/mcp")
        self.assertIn("Accept: application/json, text/event-stream", info["message"])


if __name__ == "__main__":
    unittest.main()
