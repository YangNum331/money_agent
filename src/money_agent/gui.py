from __future__ import annotations

import queue
import threading
import traceback
import webbrowser
from datetime import datetime
from tkinter import BOTH, END, LEFT, RIGHT, BooleanVar, StringVar, Tk, X, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any

import httpx

from .cli import DEFAULT_GITHUB_QUERIES
from .collectors.github import GitHubCollector
from .config import Settings
from .database import Database
from .evaluators import HeuristicEvaluator
from .filters import RuleFilter
from .service import apply_filters, evaluate_candidates, store_opportunities

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

        self._configure_styles()
        self._build_layout()
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
            text="유료 코딩 기회를 수집하고 기대수익 순으로 정리합니다.",
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

        columns = ("score", "budget", "profit", "source", "title")
        self.results = ttk.Treeview(result_panel, columns=columns, show="headings", height=9)
        self.results.heading("score", text="점수")
        self.results.heading("budget", text="예산")
        self.results.heading("profit", text="기대수익")
        self.results.heading("source", text="출처")
        self.results.heading("title", text="작업명")
        self.results.column("score", width=70, minwidth=60, anchor="center", stretch=False)
        self.results.column("budget", width=95, minwidth=80, anchor="e", stretch=False)
        self.results.column("profit", width=100, minwidth=90, anchor="e", stretch=False)
        self.results.column("source", width=90, minwidth=75, anchor="center", stretch=False)
        self.results.column("title", width=560, minwidth=260, anchor="w")
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
        self._append_log("창이 준비됐습니다. '기회 탐색 시작'을 누르세요.", "success")

    def _start_run(self) -> None:
        if self.running.get():
            return
        self.running.set(True)
        self.run_button.configure(state="disabled", text="탐색 중…")
        self.status_text.set("실행 중")
        self.summary_text.set("GitHub를 조사하고 있습니다")
        self._clear_results()
        self._append_log("새 탐색을 시작합니다.", "info")
        threading.Thread(target=self._run_pipeline, daemon=True).start()

    def _run_pipeline(self) -> None:
        try:
            settings = Settings()
            database = Database(settings.db_path)
            self._emit("log", (f"데이터베이스 준비: {settings.db_path}", "info"))
            database.initialize()

            token_state = "설정됨" if settings.github_token else "미설정(낮은 요청 한도)"
            self._emit("log", (f"GitHub 토큰: {token_state}", "warning"))
            self._emit(
                "log",
                (
                    "1/4 GitHub에서 유료 작업 후보를 찾는 중… "
                    f"(저장소 별 {settings.github_min_stars}+, "
                    f"생성 {settings.github_min_age_days}일+)",
                    "info",
                ),
            )
            collector = GitHubCollector(
                token=settings.github_token,
                min_repository_stars=settings.github_min_stars,
                min_repository_age_days=settings.github_min_age_days,
            )
            opportunities = collector.collect(queries=DEFAULT_GITHUB_QUERIES, per_query=10)
            stored = store_opportunities(database, opportunities)
            self._emit(
                "log",
                (f"수집 {stored.collected}개 · 새 항목 {stored.inserted}개", "success"),
            )

            self._emit("log", ("2/4 규칙 기반 필터를 적용하는 중…", "info"))
            filtered = apply_filters(database, RuleFilter(settings.min_budget_usd))
            self._emit(
                "log",
                (
                    f"통과 {filtered.eligible}개 · 제외 {filtered.rejected}개 "
                    f"(최소 예산 ${settings.min_budget_usd:.0f})",
                    "success",
                ),
            )

            self._emit("log", ("3/4 API 비용 없는 휴리스틱 평가를 실행하는 중…", "info"))
            evaluated = evaluate_candidates(database, HeuristicEvaluator(), limit=30)
            self._emit("log", (f"신규 평가 {evaluated.evaluated}개", "success"))

            self._emit("log", ("4/4 기대수익 순위를 계산하는 중…", "info"))
            rows = database.leaderboard(limit=10)
            stats = database.stats()
            self._emit("results", rows)
            self._emit(
                "summary",
                f"누적 {stats['total']}개 · 평가 {stats['evaluated']}개 · 상위 {len(rows)}개 표시",
            )
            if rows:
                self._emit("log", (f"완료: 상위 후보 {len(rows)}개를 표시했습니다.", "success"))
            else:
                self._emit(
                    "log",
                    ("완료: 신뢰도 조건을 충족한 유료 작업이 없습니다.", "warning"),
                )
            self._emit("done", "완료")
        except httpx.HTTPStatusError as exc:
            response = exc.response
            detail = f"GitHub API 오류 {response.status_code}"
            if response.status_code in {403, 429}:
                detail += ": 요청 한도에 도달했을 수 있습니다. .env에 GITHUB_TOKEN을 설정하세요."
            self._emit("error", detail)
        except Exception as exc:  # GUI boundary: report failures instead of crashing the window.
            self._emit("error", f"{type(exc).__name__}: {exc}")
            self._emit("log", (traceback.format_exc(), "error"))

    def _emit(self, kind: str, payload: Any) -> None:
        self.events.put((kind, payload))

    def _poll_events(self) -> None:
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
                    self.summary_text.set("실행에 실패했습니다. 아래 로그를 확인하세요.")
                    self._finish_run("오류")
        except queue.Empty:
            pass
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
            budget = float(row["budget_max"] or row["budget_min"] or 0)
            self.results.insert(
                "",
                END,
                iid=item_id,
                values=(
                    f"{float(row['opportunity_score']):.1f}",
                    f"${budget:,.2f}",
                    f"${float(row['expected_profit']):,.2f}",
                    str(row["source"]),
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


def main() -> None:
    root = Tk()
    MoneyAgentGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()

