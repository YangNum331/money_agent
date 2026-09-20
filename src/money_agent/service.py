from __future__ import annotations

from dataclasses import dataclass

from .database import Database
from .evaluators import Evaluator
from .filters import RuleFilter
from .models import Opportunity


@dataclass(slots=True)
class PipelineResult:
    collected: int = 0
    inserted: int = 0
    eligible: int = 0
    rejected: int = 0
    evaluated: int = 0


def store_opportunities(database: Database, opportunities: list[Opportunity]) -> PipelineResult:
    result = PipelineResult(collected=len(opportunities))
    for opportunity in opportunities:
        _, inserted = database.upsert_opportunity(opportunity)
        result.inserted += int(inserted)
    return result


def apply_filters(database: Database, rule_filter: RuleFilter) -> PipelineResult:
    result = PipelineResult()
    for opportunity in database.unevaluated_discovered():
        decision = rule_filter.evaluate(opportunity)
        database.set_status(opportunity.id or 0, "eligible" if decision.eligible else "rejected")
        result.eligible += int(decision.eligible)
        result.rejected += int(not decision.eligible)
    return result


def evaluate_candidates(database: Database, evaluator: Evaluator, limit: int) -> PipelineResult:
    result = PipelineResult()
    for opportunity in database.opportunities_without_evaluation(evaluator.name, limit):
        evaluation = evaluator.evaluate(opportunity)
        result.evaluated += int(database.save_evaluation(evaluation))
    return result

