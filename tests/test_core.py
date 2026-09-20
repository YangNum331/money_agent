from pathlib import Path

from money_agent.collectors.github import _repository_name, extract_usd_amounts
from money_agent.database import Database
from money_agent.evaluators import HeuristicEvaluator
from money_agent.filters import RuleFilter
from money_agent.models import Opportunity
from money_agent.ranking import expected_profit, opportunity_score
from money_agent.service import apply_filters, evaluate_candidates, store_opportunities


def sample_opportunity() -> Opportunity:
    return Opportunity(
        source="github",
        external_id="123",
        title="Python CSV parser bounty",
        description="Fix a CSV to JSON converter. Reward: $100",
        url="https://github.com/example/repo/issues/1",
        budget_min=100,
        budget_max=100,
    )


def test_extract_usd_amounts() -> None:
    assert extract_usd_amounts("Reward $50 to $125.00 USD") == [50.0, 125.0]


def test_repository_name_from_api_url() -> None:
    assert _repository_name("https://api.github.com/repos/openai/openai-python") == (
        "openai/openai-python"
    )


def test_filter_accepts_automatable_paid_task() -> None:
    decision = RuleFilter(min_budget_usd=20).evaluate(sample_opportunity())
    assert decision.eligible
    assert decision.reasons == []


def test_filter_rejects_missing_budget_and_manual_work() -> None:
    opportunity = Opportunity(
        source="github",
        external_id="x",
        title="Phone call required",
        description="Manual verification",
        url="https://example.com/x",
    )
    decision = RuleFilter().evaluate(opportunity)
    assert not decision.eligible
    assert len(decision.reasons) >= 2


def test_filter_rejects_unfunded_bounty_proposal() -> None:
    opportunity = sample_opportunity()
    opportunity.title = "[Bounty proposal] Python task ($25 proposed)"
    assert not RuleFilter().evaluate(opportunity).eligible


def test_profit_and_score_are_bounded() -> None:
    assert expected_profit(100, 0.5, 1, 5, 2) == 42
    score = opportunity_score(
        expected_profit_usd=10_000,
        automation_score=100,
        success_probability=1,
        difficulty_score=0,
        competition_risk=0,
        platform_risk=0,
        expected_hours=0,
    )
    assert score == 100


def test_heuristic_probability_includes_competition() -> None:
    opportunity = sample_opportunity()
    opportunity.id = 1
    evaluation = HeuristicEvaluator().evaluate(opportunity)
    assert 0 < evaluation.success_probability < 0.6


def test_end_to_end_pipeline(tmp_path: Path) -> None:
    database = Database(tmp_path / "test.db")
    database.initialize()
    stored = store_opportunities(database, [sample_opportunity(), sample_opportunity()])
    assert stored.collected == 2
    assert stored.inserted == 1

    filtered = apply_filters(database, RuleFilter())
    assert filtered.eligible == 1

    evaluated = evaluate_candidates(database, HeuristicEvaluator(), 10)
    assert evaluated.evaluated == 1
    assert len(database.leaderboard()) == 1
    assert database.stats() == {"eligible": 1, "evaluated": 1, "total": 1}
