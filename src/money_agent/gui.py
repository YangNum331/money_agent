from __future__ import annotations

import os
import queue
import threading
import traceback
import webbrowser
from datetime import datetime, timedelta
from tkinter import BOTH, END, LEFT, RIGHT, BooleanVar, StringVar, Tk, X, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any

from .collectors.github import GitHubCollector
from .collectors.jobicy import JobicyCollector
from .collectors.remotive import RemotiveCollector
from .config import Settings
from .database import Database
from .evaluators import HeuristicEvaluator
from .filters import RuleFilter
from .scanner import DEFAULT_GITHUB_QUERIES
from .service import apply_filters, collect_source, evaluate_candidates

WINDOW_TITLE = "MONEY_AGENT — Opportunity Scanner"
BACKGROUND = "#0d1117"
PANEL = "#161b22"
BORDER = "#30363d"
TEXT = "#e6edf3"
MUTED = "#8b949e"
ACCENT = "#2f81f7"
ACCENT_ACTIVE = "#1f6feb"
SUCCESS = "#3fb950"
WARNING = "#d29922"
ERROR = "#f85149"


class MoneyAgentGui:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry("1040x720")
        self.root.minsize(820, 580)
        self.root.configure(bg=BACKGROUND)

        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.running = BooleanVar(value=False)
        self.status_text = StringVar(value="준비됨")
        self.summary_text = StringVar(value="아직 실행하지 않았습니다")
        self.result_urls: dict[str, str] = {}
        self.closing = False

        self._configure_styles()
        self._build_layout()
        self.root.protocol("WM_DELETE_WINDOW", self._close_window)
        self.root.after(100, self._poll_events)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Root.TFrame", background=BACKGROUND)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure(
            "Title.TLabel",
            background=BACKGROUND,
            foreground=TEXT,
            font=("Segoe UI", 20, "bold"),
        )
        style.configure(
            "Subtitle.TLabel",
            background=BACKGROUND,
            foreground=MUTED,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Section.TLabel",
            background=PANEL,
            foreground=TEXT,
            font=("Segoe UI", 11, "bold"),
        )
        style.configure(
            "Status.TLabel",
            background=BACKGROUND,
            foreground=SUCCESS,
            font=("Segoe UI", 10, "bold"),
        )
        style.configure(
            "Summary.TLabel",
            background=PANEL,
            foreground=MUTED,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Run.TButton",
            background=ACCENT,
            foreground="white",
            borderwidth=0,
            padding=(22, 12),
            font=("Segoe UI", 11, "bold"),
        )
        style.map(
            "Run.TButton",
            background=[("active", ACCENT_ACTIVE), ("disabled", BORDER)],
            foreground=[("disabled", MUTED)],
        )
        style.configure(
            "Treeview",
            background=PANEL,
            fieldbackground=PANEL,
            foreground=TEXT,
            rowheight=28,
            borderwidth=0,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Treeview.Heading",
            background="#21262d",
            foreground=TEXT,
            relief="flat",
            font=("Segoe UI", 9, "bold"),
        )
        style.map("Treeview", background=[("selected", "#1f6feb")])
        style.map("Treeview.Heading", background=[("active", BORDER)])

    def _build_layout(self) -> None:
        root_frame = ttk.Frame(self.root, style="Root.TFrame", padding=24)
        root_frame.pack(fill=BOTH, expand=True)

        header = ttk.Frame(root_frame, style="Root.TFrame")
        header.pack(fill=X, pady=(0, 18))
        title_group = ttk.Frame(header, style="Root.TFrame")
        title_group.pack(side=LEFT, fill=X, expand=True)
        ttk.Label(title_group, text="MONEY_AGENT", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title_group,
            text="GitHub 보상 작업과 전 분야 원격 일자리를 찾아 가치 순으로 정리합니다.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        controls = ttk.Frame(header, style="Root.TFrame")
        controls.pack(side=RIGHT)
        ttk.Label(controls, textvariable=self.status_text, style="Status.TLabel").pack(
            side=LEFT, padx=(0, 14)
        )
        self.run_button = ttk.Button(
            controls,
            text="기회 탐색 시작",
            command=self._start_run,
            style="Run.TButton",
        )
        self.run_button.pack(side=RIGHT)

        result_panel = ttk.Frame(root_frame, style="Panel.TFrame", padding=16)
        result_panel.pack(fill=BOTH, expand=True, pady=(0, 14))
        result_header = ttk.Frame(result_panel, style="Panel.TFrame")
        result_header.pack(fill=X, pady=(0, 10))
        ttk.Label(result_header, text="상위 기회", style="Section.TLabel").pack(side=LEFT)
        ttk.Label(
            result_header,
            textvariable=self.summary_text,
            style="Summary.TLabel",
        ).pack(side=RIGHT)

        columns = ("score", "kind", "budget", "profit", "source", "title")
        self.results = ttk.Treeview(result_panel, columns=columns, show="headings", height=9)
        self.results.heading("score", text="점수")
        self.results.heading("kind", text="유형")
        self.results.heading("budget", text="보수")
        self.results.heading("profit", text="기대가치")
        self.results.heading("source", text="출처")
        self.results.heading("title", text="작업명")
        self.results.column("score", width=70, minwidth=60, anchor="center", stretch=False)
        self.results.column("kind", width=75, minwidth=65, anchor="center", stretch=False)
        self.results.column("budget", width=115, minwidth=95, anchor="e", stretch=False)
        self.results.column("profit", width=105, minwidth=90, anchor="e", stretch=False)
        self.results.column("source", width=85, minwidth=75, anchor="center", stretch=False)
        self.results.column("title", width=470, minwidth=240, anchor="w")
        self.results.pack(fill=BOTH, expand=True)
        self.results.bind("<Double-1>", self._open_selected_result)

        log_panel = ttk.Frame(root_frame, style="Panel.TFrame", padding=16)
        log_panel.pack(fill=BOTH, expand=True)
        ttk.Label(log_panel, text="실행 로그", style="Section.TLabel").pack(
            anchor="w", pady=(0, 10)
        )
        self.log = ScrolledText(
            log_panel,
            height=11,
            bg="#010409",
            fg="#c9d1d9",
            insertbackground=TEXT,
            selectbackground=ACCENT_ACTIVE,
            relief="flat",
            borderwidth=0,
            padx=12,
            pady=10,
            font=("Consolas", 9),
            state="disabled",
            wrap="word",
        )
        self.log.pack(fill=BOTH, expand=True)
        self.log.tag_configure("info", foreground="#c9d1d9")
        self.log.tag_configure("success", foreground=SUCCESS)
        self.log.tag_configure("warning", foreground=WARNING)
        self.log.tag_configure("error", foreground=ERROR)
        self._append_log(
            "창이 준비됐습니다. '기회 탐색 시작'을 누르세요.", "success"
        )

    def _start_run(self) -> None:
        if self.running.get():
            return
        self.running.set(True)
        self.run_button.configure(state="disabled", text="탐색 중…")
        self.status_text.set("실행 중")
        self.summary_text.set("세 개 출처를 조사하고 있습니다")
        self._clear_results()
        self._append_log("새 탐색을 시작합니다.", "info")
        threading.Thread(target=self._run_pipeline, daemon=True).start()

    def _run_pipeline(self) -> None:
        try:
            settings = Settings()
            database = Database(settings.db_path)
            self._emit("log", (f"데이터베이스 준비: {settings.db_path}", "info"))
            database.initialize()

            token_state = (
                "설정됨" if settings.github_token else "미설정(낮은 요청 한도)"
            )
            self._emit("log", (f"GitHub 토큰: {token_state}", "warning"))
            github = GitHubCollector(
                token=settings.github_token,
                min_repository_stars=settings.github_min_stars,
                min_repository_age_days=settings.github_min_age_days,
            )
            sources = [
                (
                    "GitHub",
                    "github",
                    timedelta(hours=1),
                    lambda: github.collect(queries=DEFAULT_GITHUB_QUERIES, per_query=10),
                ),
                ("Jobicy", "jobicy", timedelta(hours=1), lambda: JobicyCollector().collect()),
                ("Remotive", "remotive", timedelta(hours=6), RemotiveCollector().collect),
            ]
            self._emit("log", ("1/3 공개 기회 출처를 수집하는 중…", "info"))
            total_collected = 0
            total_inserted = 0
            for label, source, interval, fetch in sources:
                result = collect_source(database, source, interval, fetch)
                if result.cached:
                    self._emit(
                        "log", (f"{label}: 최근 결과 사용(호출 제한 보호)", "info")
                    )
                elif result.error:
                    self._emit("log", (f"{label}: 수집 실패 — {result.error}", "error"))
                else:
                    total_collected += result.collected
                    total_inserted += result.inserted
                    self._emit(
                        "log",
                        (
                            f"{label}: 수집 {result.collected}개 · "
                            f"새 항목 {result.inserted}개",
                            "success",
                        ),
                    )
            self._emit(
                "log",
                (
                    f"이번 실행 합계 {total_collected}개 · 신규 {total_inserted}개",
                    "success",
                ),
            )

            self._emit(
                "log",
                ("2/3 지역·직급·보수 필터와 가치 평가를 실행하는 중…", "info"),
            )
            filtered = apply_filters(database, RuleFilter(settings.min_budget_usd))
            self._emit(
                "log",
                (
                    f"통과 {filtered.eligible}개 · 제외 {filtered.rejected}개 "
                    f"(최소 예산 ${settings.min_budget_usd:.0f})",
                    "success",
                ),
            )

            evaluated = evaluate_candidates(database, HeuristicEvaluator(), limit=150)
            self._emit("log", (f"신규 평가 {evaluated.evaluated}개", "success"))

            self._emit("log", ("3/3 기회 가치 순위를 계산하는 중…", "info"))
            rows = database.leaderboard(limit=15)
            stats = database.stats()
            self._emit("results", rows)
            self._emit(
                "summary",
                f"누적 {stats['total']}개 · 평가 {stats['evaluated']}개 · "
                f"상위 {len(rows)}개 표시",
            )
            if rows:
                self._emit(
                    "log",
                    (f"완료: 상위 후보 {len(rows)}개를 표시했습니다.", "success"),
                )
            else:
                self._emit(
                    "log",
                    ("완료: 현재 조건을 충족한 기회가 없습니다.", "warning"),
                )
            self._emit("done", "완료")
        except Exception as exc:  # GUI boundary: report failures instead of crashing the window.
            self._emit("error", f"{type(exc).__name__}: {exc}")
            self._emit("log", (traceback.format_exc(), "error"))

    def _emit(self, kind: str, payload: Any) -> None:
        self.events.put((kind, payload))

    def _poll_events(self) -> None:
        if self.closing:
            return
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    message, level = payload
                    self._append_log(message, level)
                elif kind == "results":
                    self._show_results(payload)
                elif kind == "summary":
                    self.summary_text.set(payload)
                elif kind == "done":
                    self._finish_run(payload)
                elif kind == "error":
                    self._append_log(payload, "error")
                    self.summary_text.set(
                        "실행에 실패했습니다. 아래 로그를 확인하세요."
                    )
                    self._finish_run("오류")
        except queue.Empty:
            pass
        if not self.closing:
            self.root.after(100, self._poll_events)

    def _append_log(self, message: str, level: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert(END, f"[{timestamp}] {message.rstrip()}\n", level)
        self.log.configure(state="disabled")
        self.log.see(END)

    def _clear_results(self) -> None:
        self.result_urls.clear()
        for item in self.results.get_children():
            self.results.delete(item)

    def _show_results(self, rows: list[dict[str, object]]) -> None:
        self._clear_results()
        for index, row in enumerate(rows, 1):
            item_id = f"result-{index}"
            budget = _format_income(row)
            kind = "원격직" if row["kind"] == "remote_job" else "보상작업"
            self.results.insert(
                "",
                END,
                iid=item_id,
                values=(
                    f"{float(row['opportunity_score']):.1f}",
                    kind,
                    budget,
                    f"${float(row['expected_profit']):,.2f}",
                    str(row["source"]).title(),
                    str(row["title"]),
                ),
            )
            self.result_urls[item_id] = str(row["url"])

    def _open_selected_result(self, _event: object) -> None:
        selection = self.results.selection()
        if not selection:
            return
        url = self.result_urls.get(selection[0])
        if url:
            webbrowser.open(url)

    def _finish_run(self, status: str) -> None:
        self.running.set(False)
        self.status_text.set(status)
        self.run_button.configure(state="normal", text="다시 탐색")

    def _close_window(self) -> None:
        """Close the window and terminate any in-flight network worker immediately."""
        if self.closing:
            return
        self.closing = True
        try:
            self.root.quit()
            self.root.destroy()
        finally:
            # A worker can be blocked inside an OS/network call. Python daemon threads normally
            # disappear at shutdown, but a hard process exit guarantees Windows never leaves a
            # headless pythonw.exe behind after the user closes the only window.
            os._exit(0)


def _format_income(row: dict[str, object]) -> str:
    raw = row["budget_max"] or row["budget_min"]
    if raw is None:
        return "미공개"
    suffixes = {
        "one_time": "건",
        "hourly": "시간",
        "weekly": "주",
        "monthly": "월",
        "annual": "연",
        "unknown": "",
    }
    suffix = suffixes.get(str(row["income_basis"]), "")
    return f"${float(raw):,.0f}" + (f"/{suffix}" if suffix else "")


def main() -> None:
    root = Tk()
    MoneyAgentGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
