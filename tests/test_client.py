import asyncio
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from opencost_mcp.client import McpError, OpenCostClient


class FakeResponse:
    def __init__(self, body: str) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_allocation_happy_path(self) -> None:
        client = OpenCostClient("http://localhost:9090")
        with patch("opencost_mcp.client.urlopen", return_value=FakeResponse(json.dumps({"data": {}}))):
            payload = await client.get_allocation(window="7d", aggregate="namespace")
        self.assertEqual(payload, {"data": {}})

    async def test_get_allocation_http_error(self) -> None:
        client = OpenCostClient("http://localhost:9090")
        err = HTTPError(url="http://x", code=500, msg="err", hdrs=None, fp=None)
        with patch("opencost_mcp.client.urlopen", side_effect=err):
            with self.assertRaises(McpError):
                await client.get_allocation(window="7d", aggregate="namespace")


if __name__ == "__main__":
    unittest.main()
