import asyncio
from unittest.mock import AsyncMock

from opencost_mcp.tools.allocation import get_allocation_summary, get_namespace_costs, get_top_spenders
from opencost_mcp.tools.analytics import compare_time_ranges, detect_cost_spikes, get_idle_resources
from opencost_mcp.tools.forecast import check_budget_threshold, forecast_monthly_cost


class FakeClient:
    def __init__(self) -> None:
        self.get_allocation = AsyncMock(return_value={
            "data": {
                "ns-a": {"cpuCost": 10, "ramCost": 5, "totalCost": 20, "cpuEfficiency": 0.4, "ramEfficiency": 0.6, "dailyCosts": [1, 2, 3]},
                "ns-b": {"cpuCost": 2, "ramCost": 1, "totalCost": 3, "cpuEfficiency": 0.8, "ramEfficiency": 0.9, "dailyCosts": [1, 1, 1]},
            }
        })


def test_allocation_tools() -> None:
    client = FakeClient()
    text = asyncio.run(get_allocation_summary(client, "7d", "namespace"))
    assert "Allocation summary" in text
    text2 = asyncio.run(get_namespace_costs(client, "7d", "default"))
    assert "Namespace costs" in text2
    text3 = asyncio.run(get_top_spenders(client, "7d", 1))
    assert "Top 1 spenders" in text3


def test_analytics_and_forecast_tools() -> None:
    client = FakeClient()
    assert "Cost spikes" in asyncio.run(detect_cost_spikes(client))
    assert "Range comparison" in asyncio.run(compare_time_ranges(client, "a,b", "c,d"))
    assert "Idle resources" in asyncio.run(get_idle_resources(client, 0.7))
    forecast_text, projected, total = asyncio.run(forecast_monthly_cost(client))
    assert "Monthly cost forecast" in forecast_text
    assert projected
    assert total > 0
    budget_text = asyncio.run(check_budget_threshold(client, 10.0))
    assert "Budget threshold check" in budget_text
