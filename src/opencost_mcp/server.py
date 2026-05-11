"""MCP server entrypoint exposing OpenCost tools."""

from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool

from opencost_mcp.client import OpenCostClient
from opencost_mcp.schemas import (
    AllocationSummaryInput,
    CheckBudgetThresholdInput,
    CompareTimeRangesInput,
    DetectCostSpikesInput,
    ForecastMonthlyCostInput,
    IdleResourcesInput,
    NamespaceCostsInput,
    TopSpendersInput,
)
from opencost_mcp.tools.allocation import get_allocation_summary, get_namespace_costs, get_top_spenders
from opencost_mcp.tools.analytics import compare_time_ranges, detect_cost_spikes, get_idle_resources
from opencost_mcp.tools.forecast import check_budget_threshold, forecast_monthly_cost

app = Server("opencost-mcp-server")
client = OpenCostClient(os.getenv("OPENCOST_API_URL", "http://localhost:9090"))


def _schema(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "required": required, "properties": properties}


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="get_allocation_summary", description="Rank workloads by CPU/RAM/total cost and efficiency", inputSchema=_schema(["window", "aggregate"], {"window": {"type": "string"}, "aggregate": {"type": "string"}})),
        Tool(name="get_namespace_costs", description="Pod-level costs within a namespace", inputSchema=_schema(["window", "namespace"], {"window": {"type": "string"}, "namespace": {"type": "string"}})),
        Tool(name="get_top_spenders", description="Top N expensive deployments", inputSchema=_schema(["window"], {"window": {"type": "string"}, "n": {"type": "integer", "default": 10}})),
        Tool(name="detect_cost_spikes", description="Compare current vs prior window by namespace", inputSchema=_schema([], {"window": {"type": "string", "default": "7d"}, "threshold_pct": {"type": "number", "default": 20.0}})),
        Tool(name="compare_time_ranges", description="Side-by-side cost comparison for two explicit ranges", inputSchema=_schema(["range_a", "range_b"], {"range_a": {"type": "string"}, "range_b": {"type": "string"}})),
        Tool(name="get_idle_resources", description="Find low-efficiency deployments", inputSchema=_schema([], {"min_efficiency": {"type": "number", "default": 0.5}})),
        Tool(name="forecast_monthly_cost", description="Project 30-day spend from recent burn", inputSchema=_schema([], {"window": {"type": "string", "default": "7d"}})),
        Tool(name="check_budget_threshold", description="Compare projected monthly spend to budget", inputSchema=_schema(["monthly_budget"], {"monthly_budget": {"type": "number"}, "window": {"type": "string", "default": "7d"}})),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[dict[str, str]]:
    try:
        if name == "get_allocation_summary":
            inp = AllocationSummaryInput(**arguments)
            text = await get_allocation_summary(client, inp.window, inp.aggregate)
        elif name == "get_namespace_costs":
            inp = NamespaceCostsInput(**arguments)
            text = await get_namespace_costs(client, inp.window, inp.namespace)
        elif name == "get_top_spenders":
            inp = TopSpendersInput(**arguments)
            text = await get_top_spenders(client, inp.window, inp.n)
        elif name == "detect_cost_spikes":
            inp = DetectCostSpikesInput(**arguments)
            text = await detect_cost_spikes(client, inp.window, inp.threshold_pct)
        elif name == "compare_time_ranges":
            inp = CompareTimeRangesInput(**arguments)
            text = await compare_time_ranges(client, inp.range_a, inp.range_b)
        elif name == "get_idle_resources":
            inp = IdleResourcesInput(**arguments)
            text = await get_idle_resources(client, inp.min_efficiency)
        elif name == "forecast_monthly_cost":
            inp = ForecastMonthlyCostInput(**arguments)
            text, _, _ = await forecast_monthly_cost(client, inp.window)
        elif name == "check_budget_threshold":
            inp = CheckBudgetThresholdInput(**arguments)
            text = await check_budget_threshold(client, inp.monthly_budget, inp.window)
        else:
            text = f"Unknown tool: {name}"
    except (TypeError, ValueError) as exc:
        text = f"Invalid arguments for {name}: {exc}"
    except Exception as exc:
        text = f"Error running {name}: {exc}"
    return [{"type": "text", "text": text}]


async def main() -> None:
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
