from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import Evaluation, Opportunity, utc_now_iso

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS opportunities (
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
    kind TEXT NOT NULL DEFAULT 'bounty',
    income_basis TEXT NOT NULL DEFAULT 'one_time',
    organization TEXT,
    location TEXT,
    status TEXT NOT NULL DEFAULT 'discovered',
    content_hash TEXT NOT NULL,
    discovered_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source, external_id),
    UNIQUE(url)
);

CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities(status);
CREATE INDEX IF NOT EXISTS idx_opportunities_budget ON opportunities(budget_max);

CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    evaluator TEXT NOT NULL,
    automation_score REAL NOT NULL CHECK(automation_score BETWEEN 0 AND 100),
    difficulty_score REAL NOT NULL CHECK(difficulty_score BETWEEN 0 AND 100),
    success_probability REAL NOT NULL CHECK(success_probability BETWEEN 0 AND 1),
    competition_risk REAL NOT NULL CHECK(competition_risk BETWEEN 0 AND 100),
    platform_risk REAL NOT NULL CHECK(platform_risk BETWEEN 0 AND 100),
    expected_hours REAL NOT NULL,
    api_cost_estimate REAL NOT NULL,
    expected_revenue REAL NOT NULL,
    expected_profit REAL NOT NULL,
    opportunity_score REAL NOT NULL CHECK(opportunity_score BETWEEN 0 AND 100),
    reason TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(opportunity_id, evaluator, input_hash)
);

CREATE TABLE IF NOT EXISTS executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    result_json TEXT,
    api_cost REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS earnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    revenue REAL NOT NULL DEFAULT 0,
    platform_fee REAL NOT NULL DEFAULT 0,
    api_cost REAL NOT NULL DEFAULT 0,
    profit REAL NOT NULL DEFAULT 0,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_runs (
    source TEXT PRIMARY KEY,
    last_started_at TEXT NOT NULL,
    last_success_at TEXT,
    last_error TEXT,
    item_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    interval_hours REAL NOT NULL,
    status TEXT NOT NULL,
    collected INTEGER NOT NULL DEFAULT 0,
    inserted INTEGER NOT NULL DEFAULT 0,
    eligible INTEGER NOT NULL DEFAULT 0,
    rejected INTEGER NOT NULL DEFAULT 0,
    evaluated INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
"""

OPPORTUNITY_MIGRATIONS = {
    "kind": "TEXT NOT NULL DEFAULT 'bounty'",
    "income_basis": "TEXT NOT NULL DEFAULT 'one_time'",
    "organization": "TEXT",
    "location": "TEXT",
}


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterable[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            existing = {
                row["name"] for row in connection.execute("PRAGMA table_info(opportunities)")
            }
            for name, definition in OPPORTUNITY_MIGRATIONS.items():
                if name not in existing:
                    connection.execute(
                        f"ALTER TABLE opportunities ADD COLUMN {name} {definition}"
                    )

    def upsert_opportunity(self, opportunity: Opportunity) -> tuple[int, bool]:
        now = utc_now_iso()
        values = (
            opportunity.source,
            opportunity.external_id,
            opportunity.title,
            opportunity.description,
            opportunity.url,
            opportunity.budget_min,
            opportunity.budget_max,
            opportunity.currency,
            opportunity.created_at,
            json.dumps(opportunity.skills, ensure_ascii=False),
            opportunity.language,
            opportunity.kind,
            opportunity.income_basis,
            opportunity.organization,
            opportunity.location,
            opportunity.status,
            opportunity.content_hash,
            now,
            now,
        )
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT id, content_hash FROM opportunities WHERE source = ? AND external_id = ?",
                (opportunity.source, opportunity.external_id),
            ).fetchone()
            if existing is None:
                cursor = connection.execute(
                    """
                    INSERT INTO opportunities (
                        source, external_id, title, description, url, budget_min, budget_max,
                        currency, created_at, skills_json, language, kind, income_basis,
                        organization, location, status, content_hash, discovered_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                return int(cursor.lastrowid), True

            connection.execute(
                """
                UPDATE opportunities SET
                    title = ?, description = ?, url = ?, budget_min = ?, budget_max = ?,
                    currency = ?, created_at = ?, skills_json = ?, language = ?, kind = ?,
                    income_basis = ?, organization = ?, location = ?, status = ?,
                    content_hash = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    opportunity.title,
                    opportunity.description,
                    opportunity.url,
                    opportunity.budget_min,
                    opportunity.budget_max,
                    opportunity.currency,
                    opportunity.created_at,
                    json.dumps(opportunity.skills, ensure_ascii=False),
                    opportunity.language,
                    opportunity.kind,
                    opportunity.income_basis,
                    opportunity.organization,
                    opportunity.location,
                    opportunity.status,
                    opportunity.content_hash,
                    now,
                    existing["id"],
                ),
            )
            return int(existing["id"]), False

    def save_evaluation(self, evaluation: Evaluation) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO evaluations (
                    opportunity_id, evaluator, automation_score, difficulty_score,
                    success_probability, competition_risk, platform_risk, expected_hours,
                    api_cost_estimate, expected_revenue, expected_profit, opportunity_score,
                    reason, input_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluation.opportunity_id,
                    evaluation.evaluator,
                    evaluation.automation_score,
                    evaluation.difficulty_score,
                    evaluation.success_probability,
                    evaluation.competition_risk,
                    evaluation.platform_risk,
                    evaluation.expected_hours,
                    evaluation.api_cost_estimate,
                    evaluation.expected_revenue,
                    evaluation.expected_profit,
                    evaluation.opportunity_score,
                    evaluation.reason,
                    evaluation.input_hash,
                    evaluation.created_at,
                ),
            )
            return cursor.rowcount > 0

    def opportunities_without_evaluation(self, evaluator: str, limit: int) -> list[Opportunity]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT o.* FROM opportunities o
                WHERE o.status = 'eligible'
                  AND NOT EXISTS (
                    SELECT 1 FROM evaluations e
                    WHERE e.opportunity_id = o.id
                      AND e.evaluator = ?
                      AND e.input_hash = o.content_hash
                  )
                ORDER BY COALESCE(o.budget_max, o.budget_min, 0) DESC
                LIMIT ?
                """,
                (evaluator, limit),
            ).fetchall()
        return [self._row_to_opportunity(row) for row in rows]

    def set_status(self, opportunity_id: int, status: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE opportunities SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now_iso(), opportunity_id),
            )

    def unevaluated_discovered(self, limit: int = 10_000) -> list[Opportunity]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM opportunities WHERE status = 'discovered' ORDER BY id LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_opportunity(row) for row in rows]

    def leaderboard(self, limit: int = 10) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT o.id, o.source, o.title, o.url, o.budget_min, o.budget_max,
                       o.kind, o.income_basis, o.organization, o.location,
                       e.evaluator, e.opportunity_score, e.expected_profit,
                       e.success_probability, e.reason
                FROM evaluations e
                JOIN opportunities o ON o.id = e.opportunity_id
                JOIN (
                    SELECT opportunity_id, MAX(id) AS latest_id
                    FROM evaluations GROUP BY opportunity_id
                ) latest ON latest.latest_id = e.id
                ORDER BY e.opportunity_score DESC, e.expected_profit DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> dict[str, int]:
        with self.connect() as connection:
            counts = connection.execute(
                "SELECT status, COUNT(*) AS count FROM opportunities GROUP BY status"
            ).fetchall()
            evaluated = connection.execute(
                "SELECT COUNT(DISTINCT opportunity_id) FROM evaluations"
            ).fetchone()[0]
        result = {row["status"]: row["count"] for row in counts}
        result["evaluated"] = int(evaluated)
        result["total"] = sum(value for key, value in result.items() if key != "evaluated")
        return result

    def source_due(self, source: str, minimum_interval: timedelta) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT last_success_at FROM source_runs WHERE source = ?",
                (source,),
            ).fetchone()
        if row is None or not row["last_success_at"]:
            return True
        last_success = datetime.fromisoformat(row["last_success_at"])
        return datetime.now(UTC) - last_success >= minimum_interval

    def record_source_run(
        self,
        source: str,
        *,
        success: bool,
        item_count: int = 0,
        error: str | None = None,
    ) -> None:
        now = utc_now_iso()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO source_runs (
                    source, last_started_at, last_success_at, last_error, item_count
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    last_started_at = excluded.last_started_at,
                    last_success_at = CASE
                        WHEN excluded.last_success_at IS NOT NULL
                        THEN excluded.last_success_at
                        ELSE source_runs.last_success_at
                    END,
                    last_error = excluded.last_error,
                    item_count = excluded.item_count
                """,
                (source, now, now if success else None, error, item_count),
            )

    def start_scan_run(self, interval_hours: float) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO scan_runs (started_at, interval_hours, status)
                VALUES (?, ?, 'running')
                """,
                (utc_now_iso(), interval_hours),
            )
            return int(cursor.lastrowid)

    def finish_scan_run(
        self,
        run_id: int,
        *,
        status: str,
        collected: int = 0,
        inserted: int = 0,
        eligible: int = 0,
        rejected: int = 0,
        evaluated: int = 0,
        error: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE scan_runs SET
                    finished_at = ?, status = ?, collected = ?, inserted = ?,
                    eligible = ?, rejected = ?, evaluated = ?, error = ?
                WHERE id = ?
                """,
                (
                    utc_now_iso(),
                    status,
                    collected,
                    inserted,
                    eligible,
                    rejected,
                    evaluated,
                    error,
                    run_id,
                ),
            )

    def recent_scan_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM scan_runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _row_to_opportunity(row: sqlite3.Row) -> Opportunity:
        return Opportunity(
            id=row["id"],
            source=row["source"],
            external_id=row["external_id"],
            title=row["title"],
            description=row["description"],
            url=row["url"],
            budget_min=row["budget_min"],
            budget_max=row["budget_max"],
            currency=row["currency"],
            created_at=row["created_at"],
            skills=json.loads(row["skills_json"]),
            language=row["language"],
            kind=row["kind"],
            income_basis=row["income_basis"],
            organization=row["organization"],
            location=row["location"],
            status=row["status"],
        )
