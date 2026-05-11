"""Async client for OpenCost REST API using stdlib only."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from mcp.shared.exceptions import McpError
except ModuleNotFoundError:
    class McpError(Exception):
        """Fallback MCP error when MCP SDK is unavailable in test env."""



class OpenCostClient:
    """Small asynchronous wrapper around the OpenCost API."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = 30.0

    async def get_allocation(self, window: str, aggregate: str, **kwargs: Any) -> dict[str, Any]:
        params = {"window": window, "aggregate": aggregate, **kwargs}
        return await self._get("/allocation", params=params)

    async def get_assets(self, window: str) -> dict[str, Any]:
        return await self._get("/assets", params={"window": window})

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}?{urlencode(params)}"
        return await asyncio.to_thread(self._sync_get, url, path)

    def _sync_get(self, url: str, path: str) -> dict[str, Any]:
        req = Request(url=url, method="GET")
        try:
            with urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise McpError(f"Invalid OpenCost response format from {path}")
                return payload
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
            raise McpError(f"OpenCost API error ({exc.code}) for {path}: {body}") from exc
        except URLError as exc:
            raise McpError(f"Unable to reach OpenCost API at {self.base_url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise McpError(f"OpenCost API returned invalid JSON for {path}") from exc
