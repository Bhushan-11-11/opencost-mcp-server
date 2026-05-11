"""Analytical tools for cost deltas and inefficiencies."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from opencost_mcp.client import OpenCostClient
from opencost_mcp.tools.allocation import _fmt_money


def _extract_namespace_totals(payload: dict[str, Any]) -> dict[str, float]:
    data = payload.get("data", {})
    if not isinstance(data, dict):
        return {}
    return {k: float(v.get("totalCost", 0.0)) for k, v in data.items() if isinstance(v, dict)}


def _parse_window_days(window: str) -> int:
    if window.endswith("d"):
        return max(1, int(window[:-1]))
    if window.endswith("h"):
        return max(1, int(window[:-1]) // 24)
    return 7


async def detect_cost_spikes(client: OpenCostClient, window: str = "7d", threshold_pct: float = 20.0) -> str:
    """Detect namespace spikes by comparing current and prior windows."""
    days = _parse_window_days(window)
    now = datetime.now(timezone.utc)
    prior_end = now - timedelta(days=days)
    prior_start = prior_end - timedelta(days=days)

    current = await client.get_allocation(window=window, aggregate="namespace")
    prior = await client.get_allocation(
        window=f"{prior_start.isoformat()},{prior_end.isoformat()}", aggregate="namespace"
    )
    cur_totals = _extract_namespace_totals(current)
    prior_totals = _extract_namespace_totals(prior)

    all_ns = sorted(set(cur_totals) | set(prior_totals))
    lines = [f"Cost spikes (window={window}, threshold={threshold_pct:.1f}%)", "namespace | current | prior | delta% | spike"]
    for ns in all_ns:
        curr = cur_totals.get(ns, 0.0)
        prev = prior_totals.get(ns, 0.0)
        delta_pct = ((curr - prev) / prev * 100.0) if prev > 0 else (100.0 if curr > 0 else 0.0)
        spike = delta_pct > threshold_pct
        lines.append(f"{ns} | {_fmt_money(curr)} | {_fmt_money(prev)} | {delta_pct:.2f}% | {str(spike).lower()}")
    return "\n".join(lines)


async def compare_time_ranges(client: OpenCostClient, range_a: str, range_b: str) -> str:
    """Compare two explicit time ranges side by side."""
    a = await client.get_allocation(window=range_a, aggregate="namespace")
    b = await client.get_allocation(window=range_b, aggregate="namespace")
    a_totals = _extract_namespace_totals(a)
    b_totals = _extract_namespace_totals(b)

    lines = [f"Range comparison\nA={range_a}\nB={range_b}", "namespace | A | B | abs_delta | pct_delta"]
    for ns in sorted(set(a_totals) | set(b_totals)):
        av = a_totals.get(ns, 0.0)
        bv = b_totals.get(ns, 0.0)
        delta = bv - av
        pct = (delta / av * 100.0) if av else (100.0 if bv else 0.0)
        lines.append(f"{ns} | {_fmt_money(av)} | {_fmt_money(bv)} | {_fmt_money(delta)} | {pct:.2f}%")
    return "\n".join(lines)


async def get_idle_resources(client: OpenCostClient, min_efficiency: float = 0.5) -> str:
    """Return deployments with poor efficiency."""
    payload = await client.get_allocation(window="7d", aggregate="deployment")
    data = payload.get("data", {}) if isinstance(payload.get("data", {}), dict) else {}
    rows = []
    for name, item in data.items():
        if not isinstance(item, dict):
            continue
        cpu_eff = float(item.get("cpuEfficiency", 0.0))
        ram_eff = float(item.get("ramEfficiency", 0.0))
        if cpu_eff < min_efficiency or ram_eff < min_efficiency:
            total = float(item.get("totalCost", 0.0))
            wasted = total * (1.0 - max(cpu_eff, ram_eff))
            rows.append((name, cpu_eff, ram_eff, wasted, total))
    rows.sort(key=lambda x: x[3], reverse=True)
    lines = [f"Idle resources (min_efficiency={min_efficiency:.2f})", "deployment | cpu_eff | ram_eff | wasted | total"]
    for r in rows:
        lines.append(f"{r[0]} | {r[1]:.2f} | {r[2]:.2f} | {_fmt_money(r[3])} | {_fmt_money(r[4])}")
    return "\n".join(lines)
