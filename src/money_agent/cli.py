from __future__ import annotations

import argparse
import json
import sys

from .collectors.github import GitHubCollector
from .config import Settings
from .database import Database
from .evaluators import HeuristicEvaluator, OpenAICompatibleEvaluator
from .filters import RuleFilter
from .scanner import DEFAULT_GITHUB_QUERIES, collect_all_sources
from .service import (
    SourceResult,
    apply_filters,
    evaluate_candidates,
    store_opportunities,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="money-agent")
    parser.add_argument("--db", help="SQLite path (default: MONEY_AGENT_DB)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create or migrate the local database")

    collect = subparsers.add_parser("collect-github", help="Collect paid GitHub issues")
    collect.add_argument("--query", action="append", dest="queries")
    collect.add_argument("--per-query", type=int, default=30)
    collect.add_argument("--min-stars", type=int)
    collect.add_argument("--min-age-days", type=int)

    collect_all = subparsers.add_parser(
        "collect-all", help="Collect GitHub bounties and broad remote jobs"
    )
    collect_all.add_argument("--force", action="store_true")

    run = subparsers.add_parser("run", help="Collect, filter, evaluate, and show rankings")
    run.add_argument("--query", action="append", dest="queries")
    run.add_argument("--per-query", type=int, default=30)
    run.add_argument("--min-stars", type=int)
    run.add_argument("--min-age-days", type=int)
    run.add_argument("--evaluate-limit", type=int, default=30)
    run.add_argument("--top", type=int, default=5)
    run.add_argument("--evaluator", choices=("heuristic", "llm"), default="heuristic")
    run.add_argument("--force", action="store_true", help="Ignore source refresh intervals")

    rank = subparsers.add_parser("rank", help="Show saved top opportunities")
    rank.add_argument("--top", type=int, default=10)
    rank.add_argument("--json", action="store_true")

    subparsers.add_parser("stats", help="Show pipeline counts")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings()
    if args.db:
        settings.db_path = settings.db_path.__class__(args.db)
    database = Database(settings.db_path)
    database.initialize()

    if args.command == "init-db":
        print(f"Database ready: {settings.db_path}")
        return 0

    if args.command == "collect-github":
        result = _collect(
            database,
            settings,
            args.queries,
            args.per_query,
            args.min_stars,
            args.min_age_days,
        )
        print(f"Collected {result.collected}; inserted {result.inserted}")
        return 0

    if args.command == "collect-all":
        results = collect_all_sources(database, settings, force=args.force)
        _print_collection_results(results)
        return 0 if any(not result.error for result in results) else 1

    if args.command == "run":
        results = collect_all_sources(
            database,
            settings,
            queries=args.queries,
            per_query=args.per_query,
            min_stars=args.min_stars,
            min_age_days=args.min_age_days,
            force=args.force,
        )
        filtered = apply_filters(database, RuleFilter(settings.min_budget_usd))
        evaluator = _make_evaluator(args.evaluator, settings)
        evaluated = evaluate_candidates(database, evaluator, args.evaluate_limit)
        collected = sum(result.collected for result in results)
        inserted = sum(result.inserted for result in results)
        _print_collection_results(results)
        print(
            f"Collected {collected} ({inserted} new); "
            f"eligible {filtered.eligible}; rejected {filtered.rejected}; "
            f"evaluated {evaluated.evaluated}"
        )
        _print_rankings(database.leaderboard(args.top))
        return 0

    if args.command == "rank":
        rows = database.leaderboard(args.top)
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        else:
            _print_rankings(rows)
        return 0

    if args.command == "stats":
        print(json.dumps(database.stats(), indent=2, ensure_ascii=False))
        return 0
    return 2


def _collect(
    database: Database,
    settings: Settings,
    queries: list[str] | None,
    per_query: int,
    min_stars: int | None,
    min_age_days: int | None,
):
    collector = GitHubCollector(
        token=settings.github_token,
        min_repository_stars=(
            settings.github_min_stars if min_stars is None else max(min_stars, 0)
        ),
        min_repository_age_days=(
            settings.github_min_age_days if min_age_days is None else max(min_age_days, 0)
        ),
    )
    opportunities = collector.collect(
        queries=queries or DEFAULT_GITHUB_QUERIES,
        per_query=per_query,
    )
    return store_opportunities(database, opportunities)


def _print_collection_results(results: list[SourceResult]) -> None:
    for result in results:
        if result.cached:
            print(f"{result.source}: cached")
        elif result.error:
            print(f"{result.source}: ERROR {result.error}")
        else:
            print(f"{result.source}: {result.collected} collected, {result.inserted} new")


def _make_evaluator(kind: str, settings: Settings):
    if kind == "heuristic":
        return HeuristicEvaluator()
    if not settings.llm_api_key:
        raise SystemExit("LLM_API_KEY is required for --evaluator llm")
    return OpenAICompatibleEvaluator(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
    )


def _print_rankings(rows: list[dict[str, object]]) -> None:
    if not rows:
        print("No evaluated opportunities yet.")
        return
    print("\nTOP OPPORTUNITIES")
    for index, row in enumerate(rows, 1):
        budget = row["budget_max"] or row["budget_min"] or 0
        print(
            f"{index}. [{float(row['opportunity_score']):.1f}] {row['title']}\n"
            f"   ${float(budget):.2f} | expected profit ${float(row['expected_profit']):.2f}\n"
            f"   {row['url']}"
        )


if __name__ == "__main__":
    sys.exit(main())
