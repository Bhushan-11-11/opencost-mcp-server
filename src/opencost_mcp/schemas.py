"""Dataclass models for MCP tool inputs."""

from dataclasses import dataclass


@dataclass(slots=True)
class AllocationSummaryInput:
    window: str
    aggregate: str


@dataclass(slots=True)
class NamespaceCostsInput:
    window: str
    namespace: str


@dataclass(slots=True)
class TopSpendersInput:
    window: str
    n: int = 10


@dataclass(slots=True)
class DetectCostSpikesInput:
    window: str = "7d"
    threshold_pct: float = 20.0


@dataclass(slots=True)
class CompareTimeRangesInput:
    range_a: str = ""
    range_b: str = ""


@dataclass(slots=True)
class IdleResourcesInput:
    min_efficiency: float = 0.5


@dataclass(slots=True)
class ForecastMonthlyCostInput:
    window: str = "7d"


@dataclass(slots=True)
class CheckBudgetThresholdInput:
    monthly_budget: float = 0.0
    window: str = "7d"
