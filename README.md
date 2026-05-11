# opencost-mcp-server

`opencost-mcp-server` is a production-ready Model Context Protocol (MCP) server that lets AI agents query Kubernetes cost and efficiency insights from OpenCost through clean, structured tools.

**Feature highlight:** No dependencies beyond the MCP SDK for runtime operation, making it friendly for restricted network environments and cautious supply-chain policies.

## Prerequisites

Run OpenCost in your cluster and expose it locally:

```bash
kubectl port-forward -n opencost svc/opencost 9090:9090
```

You can also use `https://demo.opencost.io` for development.

## Installation

```bash
pip install opencost-mcp-server
```

```bash
uvx opencost-mcp-server
```

## Development setup

```bash
pip install -e ".[test]"
pytest -q
```

## Claude Desktop configuration

```json
{
  "mcpServers": {
    "opencost": {
      "command": "uvx",
      "args": ["opencost-mcp-server"],
      "env": { "OPENCOST_API_URL": "http://localhost:9090" }
    }
  }
}
```

## Example prompts

- "Show me the top 10 spenders by deployment over 7d."
- "Find namespace cost spikes over 20% in the last week."
- "Forecast monthly spend and check against a $12,000 budget."

## Tools

- `get_allocation_summary`: Ranked workloads with CPU/RAM/total costs and efficiency.
- `get_namespace_costs`: Pod-level cost breakdown for one namespace.
- `get_top_spenders`: Top-N expensive deployments by total cost.
- `detect_cost_spikes`: Compares current window against a prior window and flags spikes.
- `compare_time_ranges`: Side-by-side cost comparison of explicit ranges.
- `get_idle_resources`: Low-efficiency deployments sorted by wasted spend.
- `forecast_monthly_cost`: 30-day projection by namespace and total.
- `check_budget_threshold`: Budget status with top contributors.
