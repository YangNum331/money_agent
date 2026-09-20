# MONEY_AGENT

MONEY_AGENT is a local-first, human-gated system that discovers online earning opportunities, removes poor candidates cheaply, and ranks the remainder by expected economic value.

Version 0.3 includes:

- paid GitHub issue collection through the official API;
- broad remote-job collection from the public Jobicy and Remotive APIs, including writing, design, marketing, customer support, translation, operations, and technical roles;
- SQLite persistence and source-level deduplication;
- one-hour source caching for GitHub and Jobicy and six-hour caching for Remotive;
- rule-based budget, location, seniority, task-type, and risk filtering;
- salary normalization across hourly, weekly, monthly, annual, and one-time payments;
- zero-API-cost heuristic evaluation;
- optional OpenAI-compatible JSON evaluation;
- expected-profit and opportunity-score ranking;
- a CLI leaderboard;
- a Windows desktop UI with live execution logs and a ranked results table;
- a persistent background scanner that runs immediately and then every six hours;
- rotating UTF-8 logs, durable scan history, duplicate-instance protection, and restart recovery;
- Windows sign-in startup scripts and a Docker deployment for an always-on server;
- no bids, pull requests, messages, payments, or other external actions.

The estimates are decision aids, not promises of income. Platform rules, bounty terms, tax obligations, and submission requirements still need human review.

## Quick start

Python 3.11 or newer is required.

### Windows one-click UI

1. Install Python 3.11 or newer from python.org and enable `Add Python to PATH`.
2. Double-click `run_gui.bat` in the project folder.
3. In the MONEY_AGENT window, click **기회 탐색 시작**. One click scans all three sources.

The first launch creates `.venv` and installs the small set of dependencies. Later launches reuse it. The window remains responsive while collection runs, streams each pipeline stage into the log, and shows the top opportunities in a table. Double-click a result row to open its source page.

For a higher GitHub API rate limit, copy `.env.example` to `.env` and set `GITHUB_TOKEN`. The UI still works without it, but GitHub may limit repeated searches.

### Windows 24-hour scanner

1. Double-click `start_24h.bat` once. It runs in the background and performs the first scan immediately.
2. Double-click `install_24h_startup.bat` if it should restart automatically whenever you sign in to Windows.
3. Open `logs/money_agent.log` to inspect timestamped source results and the top ten opportunities.
4. Double-click `stop_24h.bat` to stop only the MONEY_AGENT background process.

All opportunities remain in `data/money_agent.db`, and every cycle is also recorded in the `scan_runs` table. Log files rotate at 5 MB and keep five backups. Starting it twice is safe: the second process detects the existing scanner and exits.

The Windows scanner only works while the PC is powered on and awake. Sleep, shutdown, or loss of internet pauses collection; Windows startup resumes it after the next sign-in.

### Docker server

On an always-on computer or VPS with Docker:

```bash
docker compose up -d --build
docker compose logs -f
```

The container restarts automatically unless manually stopped. The database and log directories are mounted outside the container, so upgrades do not erase them.

### Command line

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env  # On Windows, copy this file manually or use Copy-Item
```

The CLI loads `.env` from the current directory. A GitHub token is optional but strongly recommended because unauthenticated search has a low rate limit.

```bash
money-agent init-db
money-agent run --per-query 20 --top 10
money-agent collect-all
money-agent stats
money-agent rank --top 10
```

Custom searches can be supplied repeatedly:

```bash
money-agent collect-github --query 'label:bounty python' --query '"reward" API'
```

By default, results from forks, archived projects, repositories under 180 days old, and repositories with fewer than 10 stars are ignored as a basic credibility check. Override these for exploration with `--min-stars 0 --min-age-days 0`; doing so increases spam and payment risk. These checks do not prove that a bounty is legitimate.

To use an OpenAI-compatible provider, set `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL`, then run:

```bash
money-agent run --evaluator llm --evaluate-limit 10
```

The default heuristic evaluator makes no paid model calls. Evaluations are cached by opportunity content hash, evaluator, and model name. Use `--force` only when you intentionally want to bypass source refresh intervals.

## Sources and attribution

- GitHub results retain and open the original issue URL.
- Jobicy results come from [Jobicy's public remote-jobs API](https://jobicy.com/jobs-rss-feed) and retain the original listing URL.
- Remotive results come from [Remotive's public remote-jobs API](https://github.com/remotive-com/remote-jobs-api) and retain the original Remotive listing URL.

The app only indexes public listings. It does not scrape login-only marketplaces or claim that a listing is legitimate. Always verify eligibility, contract terms, payment method, local tax obligations, and whether the employer accepts applicants in Korea.

## Safety boundary

v0.3 only reads public opportunity data and writes to a local SQLite database. It does not:

- submit bids or pull requests;
- send client messages;
- accept contracts;
- solve CAPTCHAs or bypass access controls;
- access payment accounts;
- execute third-party task code.

All future external side effects must remain behind an explicit human approval gate.

## Score meaning

Expected profit is estimated as:

```text
revenue × success probability − API cost − platform cost − risk cost
```

For a remote job, the comparable revenue basis is one month of annual/monthly salary or one week of hourly/weekly pay. The expected value is then weighted by a deliberately conservative application-success estimate. A missing salary is displayed as `미공개` and contributes no estimated monetary value.

Opportunity score is a 0–100 prioritization score combining expected profit, automation potential, success probability, difficulty, competition, platform risk, and estimated time. The v0.3 coefficients are provisional and should be recalibrated from real outcomes.

## Development

```bash
pytest
ruff check .
```

## Roadmap

1. Add user-editable region, role, and keyword preferences in the desktop UI.
2. Add more sources only when a stable official API and acceptable terms are available.
3. Add outcome tracking so ranking coefficients can be calibrated from real applications.
4. Add an approval inbox before any external submission capability.
