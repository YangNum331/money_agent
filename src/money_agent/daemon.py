from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import sys
import threading
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import Settings
from .database import Database
from .evaluators import HeuristicEvaluator
from .filters import RuleFilter
from .scanner import collect_all_sources
from .service import SourceResult, apply_filters, evaluate_candidates

LOGGER_NAME = "money_agent.daemon"
LOCK_PORT = 45871


@dataclass(slots=True)
class ScanSummary:
    run_id: int
    status: str
    collected: int
    inserted: int
    eligible: int
    rejected: int
    evaluated: int
    source_results: list[SourceResult]
    leaders: list[dict[str, object]]


def configure_logging(path: Path) -> logging.Logger:
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    if sys.stdout is not None:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    return logger


def run_scan_cycle(settings: Settings, logger: logging.Logger) -> ScanSummary:
    database = Database(settings.db_path)
    database.initialize()
    run_id = database.start_scan_run(settings.scan_interval_hours)
    logger.info("검색 #%s 시작", run_id)
    try:
        source_results = collect_all_sources(database, settings)
        for result in source_results:
            if result.cached:
                logger.info("%s: 최근 수집 결과 사용", result.source)
            elif result.error:
                logger.error("%s: 수집 실패 | %s", result.source, result.error)
            else:
                logger.info(
                    "%s: %s개 수집, %s개 신규",
                    result.source,
                    result.collected,
                    result.inserted,
                )

        filtered = apply_filters(database, RuleFilter(settings.min_budget_usd))
        evaluated = evaluate_candidates(database, HeuristicEvaluator(), limit=200)
        leaders = database.leaderboard(limit=10)
        collected = sum(result.collected for result in source_results)
        inserted = sum(result.inserted for result in source_results)
        failures = sum(result.error is not None for result in source_results)
        if failures == len(source_results):
            status = "failed"
        elif failures:
            status = "partial"
        else:
            status = "success"
        error = "; ".join(
            f"{result.source}: {result.error}" for result in source_results if result.error
        )
        database.finish_scan_run(
            run_id,
            status=status,
            collected=collected,
            inserted=inserted,
            eligible=filtered.eligible,
            rejected=filtered.rejected,
            evaluated=evaluated.evaluated,
            error=error or None,
        )
        logger.info(
            "검색 #%s 완료 | 상태=%s 수집=%s 신규=%s 통과=%s 제외=%s 평가=%s",
            run_id,
            status,
            collected,
            inserted,
            filtered.eligible,
            filtered.rejected,
            evaluated.evaluated,
        )
        for index, row in enumerate(leaders, 1):
            logger.info(
                "TOP %s | 점수 %.1f | %s | %s",
                index,
                float(row["opportunity_score"]),
                row["title"],
                row["url"],
            )
        return ScanSummary(
            run_id=run_id,
            status=status,
            collected=collected,
            inserted=inserted,
            eligible=filtered.eligible,
            rejected=filtered.rejected,
            evaluated=evaluated.evaluated,
            source_results=source_results,
            leaders=leaders,
        )
    except Exception as exc:
        database.finish_scan_run(
            run_id,
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
        )
        logger.exception("검색 #%s 처리 중 예외", run_id)
        raise


def run_forever(
    settings: Settings,
    logger: logging.Logger,
    *,
    interval_hours: float,
    stop_event: threading.Event,
    once: bool = False,
) -> None:
    interval_seconds = interval_hours * 60 * 60
    while not stop_event.is_set():
        try:
            run_scan_cycle(settings, logger)
        except Exception:
            # The failure is persisted and logged; the next scheduled cycle still runs.
            pass
        if once:
            break
        # Wait after completion so Remotive's six-hour source limit is never polled early.
        logger.info("다음 검색까지 %.1f시간 대기", interval_hours)
        stop_event.wait(interval_seconds)


def _acquire_instance_lock() -> socket.socket:
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", LOCK_PORT))
        lock.listen(1)
    except OSError as exc:
        lock.close()
        raise RuntimeError("MONEY_AGENT 24시간 검색기가 이미 실행 중입니다.") from exc
    return lock


def _write_pid(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(os.getpid()), encoding="ascii")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="money-agent-daemon")
    parser.add_argument("--interval-hours", type=float, help="Search interval (minimum 6)")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings()
    interval = args.interval_hours or settings.scan_interval_hours
    if not args.once and interval < 6:
        raise SystemExit("Continuous mode requires an interval of at least 6 hours.")
    logger = configure_logging(settings.daemon_log_path)
    settings.scan_interval_hours = interval
    try:
        lock = _acquire_instance_lock()
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 2

    stop_event = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        logger.info("종료 신호를 받았습니다.")
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    _write_pid(settings.daemon_pid_path)
    logger.info("MONEY_AGENT 24시간 검색기 시작 | 검색 주기 %.1f시간", interval)
    try:
        run_forever(
            settings,
            logger,
            interval_hours=interval,
            stop_event=stop_event,
            once=args.once,
        )
    finally:
        lock.close()
        settings.daemon_pid_path.unlink(missing_ok=True)
        logger.info("MONEY_AGENT 24시간 검색기 종료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
