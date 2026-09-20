from __future__ import annotations

from datetime import timedelta

from .collectors.github import GitHubCollector
from .collectors.jobicy import JobicyCollector
from .collectors.remotive import RemotiveCollector
from .config import Settings
from .database import Database
from .service import SourceResult, collect_source

DEFAULT_GITHUB_QUERIES = [
    'label:bounty (python OR javascript OR "bug fix")',
    '"bounty" (automation OR script OR API)',
    '"reward" (python OR javascript OR API)',
]


def collect_all_sources(
    database: Database,
    settings: Settings,
    *,
    queries: list[str] | None = None,
    per_query: int = 10,
    min_stars: int | None = None,
    min_age_days: int | None = None,
    force: bool = False,
) -> list[SourceResult]:
    github = GitHubCollector(
        token=settings.github_token,
        min_repository_stars=(
            settings.github_min_stars if min_stars is None else max(min_stars, 0)
        ),
        min_repository_age_days=(
            settings.github_min_age_days if min_age_days is None else max(min_age_days, 0)
        ),
    )
    definitions = [
        (
            "github",
            timedelta(hours=1),
            lambda: github.collect(
                queries=queries or DEFAULT_GITHUB_QUERIES,
                per_query=per_query,
            ),
        ),
        ("jobicy", timedelta(hours=1), lambda: JobicyCollector().collect()),
        ("remotive", timedelta(hours=6), RemotiveCollector().collect),
    ]
    return [
        collect_source(database, source, interval, fetch, force=force)
        for source, interval, fetch in definitions
    ]
