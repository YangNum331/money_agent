import sqlite3
from datetime import timedelta
from pathlib import Path

from money_agent.collectors.common import parse_usd_salary
from money_agent.collectors.github import _repository_name, extract_usd_amounts
from money_agent.collectors.jobicy import JobicyCollector
from money_agent.collectors.remotive import RemotiveCollector
from money_agent.config import Settings
from money_agent.daemon import configure_logging, run_scan_cycle
from money_agent.database import Database
from money_agent.evaluators import HeuristicEvaluator, normalized_income_value
from money_agent.filters import RuleFilter
from money_agent.gui import MoneyAgentGui
from money_agent.models import Opportunity
from money_agent.ranking import expected_profit, opportunity_score
from money_agent.service import (
    SourceResult,
    apply_filters,
    collect_source,
    evaluate_candidates,
    store_opportunities,
)


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


def test_parse_salary_ignores_unrelated_hours() -> None:
    assert parse_usd_salary("$90k - $105k, 35-40 hours per week") == (90_000, 105_000)
    assert parse_usd_salary("$25/hour") == (25, 25)


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
    opportunity.title = "Proposed $25 documentation bounty"
    assert not RuleFilter().evaluate(opportunity).eligible


def test_remote_filter_accepts_global_and_rejects_senior_role() -> None:
    opportunity = Opportunity(
        source="jobicy",
        external_id="remote-1",
        title="Customer support specialist",
        description="Help customers through email.",
        url="https://example.com/remote-1",
        kind="remote_job",
        income_basis="annual",
        location="Worldwide",
    )
    assert RuleFilter().evaluate(opportunity).eligible
    opportunity.title = "Senior customer support manager"
    assert not RuleFilter().evaluate(opportunity).eligible


def test_collectors_normalize_remote_jobs() -> None:
    jobicy = JobicyCollector._normalize(
        {
            "id": 7,
            "jobTitle": "Writer",
            "jobDescription": "<p>Write helpful guides.</p>",
            "url": "https://jobicy.com/jobs/7",
            "salaryMin": 40_000,
            "salaryMax": 60_000,
            "salaryCurrency": "USD",
            "salaryPeriod": "yearly",
            "jobGeo": "Anywhere",
            "companyName": "Example",
        }
    )
    assert jobicy.kind == "remote_job"
    assert jobicy.income_basis == "annual"
    assert jobicy.description == "Write helpful guides."

    remotive = RemotiveCollector._normalize(
        {
            "id": 8,
            "title": "Editor",
            "description": "<div>Edit articles.</div>",
            "url": "https://remotive.com/jobs/8",
            "salary": "$25/hour",
            "candidate_required_location": "Worldwide",
        }
    )
    assert remotive.budget_min == 25
    assert remotive.location == "Worldwide"


def test_income_is_normalized_to_comparable_value() -> None:
    opportunity = sample_opportunity()
    opportunity.kind = "remote_job"
    opportunity.budget_min = 120_000
    opportunity.budget_max = 120_000
    opportunity.income_basis = "annual"
    assert normalized_income_value(opportunity) == 10_000
    opportunity.budget_min = opportunity.budget_max = 25
    opportunity.income_basis = "hourly"
    assert normalized_income_value(opportunity) == 1_000


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


def test_source_refresh_interval_uses_cache(tmp_path: Path) -> None:
    database = Database(tmp_path / "cache.db")
    database.initialize()
    calls = 0

    def fetch() -> list[Opportunity]:
        nonlocal calls
        calls += 1
        return [sample_opportunity()]

    first = collect_source(database, "example", timedelta(hours=1), fetch)
    second = collect_source(database, "example", timedelta(hours=1), fetch)
    assert first.inserted == 1
    assert second.cached
    assert calls == 1


def test_database_migrates_v01_opportunities(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            external_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            url TEXT NOT NULL,
            budget_min REAL,
            budget_max REAL,
            currency TEXT NOT NULL DEFAULT 'USD',
            created_at TEXT,
            skills_json TEXT NOT NULL DEFAULT '[]',
            language TEXT,
            status TEXT NOT NULL DEFAULT 'discovered',
            content_hash TEXT NOT NULL,
            discovered_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source, external_id),
            UNIQUE(url)
        )
        """
    )
    connection.commit()
    connection.close()

    Database(path).initialize()
    connection = sqlite3.connect(path)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(opportunities)")}
    connection.close()
    assert {"kind", "income_basis", "organization", "location"} <= columns


def test_gui_close_terminates_process(monkeypatch) -> None:
    calls: list[str] = []

    class FakeRoot:
        def quit(self) -> None:
            calls.append("quit")

        def destroy(self) -> None:
            calls.append("destroy")

    app = MoneyAgentGui.__new__(MoneyAgentGui)
    app.root = FakeRoot()
    app.closing = False
    monkeypatch.setattr("money_agent.gui.os._exit", lambda code: calls.append(f"exit:{code}"))

    app._close_window()

    assert calls == ["quit", "destroy", "exit:0"]
    assert app.closing


def test_daemon_cycle_persists_history_and_log(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(
        db_path=tmp_path / "daemon.db",
        daemon_log_path=tmp_path / "money_agent.log",
        daemon_pid_path=tmp_path / "daemon.pid",
    )
    source_results = [
        SourceResult(source="github", collected=3, inserted=2),
        SourceResult(source="jobicy", collected=10, inserted=4),
        SourceResult(source="remotive", error="temporary failure"),
    ]
    monkeypatch.setattr(
        "money_agent.daemon.collect_all_sources",
        lambda _database, _settings: source_results,
    )
    logger = configure_logging(settings.daemon_log_path)

    summary = run_scan_cycle(settings, logger)

    for handler in logger.handlers:
        handler.close()
    assert summary.status == "partial"
    assert summary.collected == 13
    assert summary.inserted == 6
    history = Database(settings.db_path).recent_scan_runs()
    assert history[0]["status"] == "partial"
    assert history[0]["finished_at"] is not None
    log_text = settings.daemon_log_path.read_text(encoding="utf-8")
    assert "검색 #1 완료" in log_text
    assert "remotive: 수집 실패" in log_text
