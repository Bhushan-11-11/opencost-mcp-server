"""Allocation-oriented tool functions."""

from __future__ import annotations

from typing import Any

from opencost_mcp.client import OpenCostClient


def _iter_allocation_rows(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    data = payload.get("data", {})
    if isinstance(data, dict):
        return [(k, v) for k, v in data.items() if isinstance(v, dict)]
    return []


def _fmt_money(value: float) -> str:
    return f"${value:.2f}"


async def get_allocation_summary(client: OpenCostClient, window: str, aggregate: str) -> str:
    """Return ranked allocation summary."""
    payload = await client.get_allocation(window=window, aggregate=aggregate, accumulate="true")
    rows = []
    for name, item in _iter_allocation_rows(payload):
        cpu = float(item.get("cpuCost", 0.0))
        ram = float(item.get("ramCost", 0.0))
        total = float(item.get("totalCost", cpu + ram))
        eff = max(float(item.get("cpuEfficiency", 0.0)), float(item.get("ramEfficiency", 0.0))) * 100
        rows.append((name, cpu, ram, total, eff))
    rows.sort(key=lambda x: x[3], reverse=True)

    lines = [f"Allocation summary ({window}, aggregate={aggregate})", "rank | workload | cpu | ram | total | efficiency%"]
    for idx, row in enumerate(rows, 1):
        lines.append(f"{idx} | {row[0]} | {_fmt_money(row[1])} | {_fmt_money(row[2])} | {_fmt_money(row[3])} | {row[4]:.1f}%")
    return "\n".join(lines)


async def get_namespace_costs(client: OpenCostClient, window: str, namespace: str) -> str:
    """Return pod-level breakdown for a namespace."""
    payload = await client.get_allocation(window=window, aggregate="pod", filterNamespaces=namespace)
    rows = []
    for pod, item in _iter_allocation_rows(payload):
        total = float(item.get("totalCost", 0.0))
        cpu = float(item.get("cpuCost", 0.0))
        ram = float(item.get("ramCost", 0.0))
        rows.append((pod, cpu, ram, total))
    rows.sort(key=lambda x: x[3], reverse=True)
    lines = [f"Namespace costs ({namespace}, {window})", "pod | cpu | ram | total"]
    for pod, cpu, ram, total in rows:
        lines.append(f"{pod} | {_fmt_money(cpu)} | {_fmt_money(ram)} | {_fmt_money(total)}")
    return "\n".join(lines)


async def get_top_spenders(client: OpenCostClient, window: str, n: int = 10) -> str:
    """Return top N spenders by deployment."""
    payload = await client.get_allocation(window=window, aggregate="deployment")
    rows = []
    for name, item in _iter_allocation_rows(payload):
        rows.append((name, float(item.get("totalCost", 0.0))))
    rows.sort(key=lambda x: x[1], reverse=True)
    lines = [f"Top {n} spenders ({window})", "rank | deployment | total"]
    for idx, (name, total) in enumerate(rows[:n], 1):
        lines.append(f"{idx} | {name} | {_fmt_money(total)}")
    return "\n".join(lines)
