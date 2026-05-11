"""Forecasting and budget tools."""

from __future__ import annotations

from typing import Any

from opencost_mcp.client import OpenCostClient
from opencost_mcp.tools.allocation import _fmt_money


def _extract_daily_by_namespace(payload: dict[str, Any]) -> dict[str, list[float]]:
    data = payload.get("data", {})
    if not isinstance(data, dict):
        return {}
    out: dict[str, list[float]] = {}
    for ns, item in data.items():
        if not isinstance(item, dict):
            continue
        hist = item.get("dailyCosts")
        if isinstance(hist, list):
            out[ns] = [float(v) for v in hist]
        else:
            out[ns] = [float(item.get("totalCost", 0.0))]
    return out


async def forecast_monthly_cost(client: OpenCostClient, window: str = "7d") -> tuple[str, dict[str, float], float]:
    """Forecast monthly costs from daily burn rates."""
    payload = await client.get_allocation(window=window, aggregate="namespace")
    series = _extract_daily_by_namespace(payload)
    projected: dict[str, float] = {}
    for ns, vals in series.items():
        avg = sum(vals) / max(1, len(vals))
        projected[ns] = avg * 30.0
    total = sum(projected.values())

    lines = [f"Monthly cost forecast (window={window})", "namespace | projected_monthly"]
    for ns, cost in sorted(projected.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"{ns} | {_fmt_money(cost)}")
    lines.append(f"TOTAL | {_fmt_money(total)}")
    return "\n".join(lines), projected, total


async def check_budget_threshold(client: OpenCostClient, monthly_budget: float, window: str = "7d") -> str:
    """Check whether projected monthly spend exceeds budget."""
    summary, projected, total = await forecast_monthly_cost(client=client, window=window)
    pct = (total / monthly_budget) * 100.0 if monthly_budget else 0.0
    over = total > monthly_budget
    top = sorted(projected.items(), key=lambda x: x[1], reverse=True)[:5]
    lines = [
        "Budget threshold check",
        f"Projected monthly cost: {_fmt_money(total)}",
        f"Budget: {_fmt_money(monthly_budget)}",
        f"Budget consumed: {pct:.2f}%",
        f"Over budget: {str(over).lower()}",
        "Top contributors:",
    ]
    lines.extend([f"- {ns}: {_fmt_money(cost)}" for ns, cost in top])
    lines.append("")
    lines.append(summary)
    return "\n".join(lines)
