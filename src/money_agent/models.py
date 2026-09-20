from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class Opportunity:
    source: str
    external_id: str
    title: str
    description: str
    url: str
    budget_min: float | None = None
    budget_max: float | None = None
    currency: str = "USD"
    created_at: str | None = None
    skills: list[str] = field(default_factory=list)
    language: str | None = None
    status: str = "discovered"
    id: int | None = None

    @property
    def content_hash(self) -> str:
        canonical = "\n".join(
            [self.source, self.external_id, self.title.strip(), self.description.strip()]
        )
        return sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def midpoint_budget(self) -> float | None:
        values = [value for value in (self.budget_min, self.budget_max) if value is not None]
        return sum(values) / len(values) if values else None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Evaluation:
    opportunity_id: int
    evaluator: str
    automation_score: float
    difficulty_score: float
    success_probability: float
    competition_risk: float
    platform_risk: float
    expected_hours: float
    api_cost_estimate: float
    expected_revenue: float
    expected_profit: float
    opportunity_score: float
    reason: str
    input_hash: str
    created_at: str = field(default_factory=utc_now_iso)
    id: int | None = None

