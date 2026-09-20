# MONEY_AGENT

MONEY_AGENT is a local-first, human-gated system that discovers paid technical work, removes poor candidates cheaply, and ranks the remainder by expected economic value.

This repository currently implements the first executable slice of v0.1:

- paid GitHub issue collection through the official API;
- SQLite persistence and source-level deduplication;
- rule-based budget, task-type, and risk filtering;
- zero-API-cost heuristic evaluation;
- optional OpenAI-compatible JSON evaluation;
- expected-profit and opportunity-score ranking;
- a CLI leaderboard;
- no bids, pull requests, messages, payments, or other external actions.

The estimates are decision aids, not promises of income. Platform rules, bounty terms, tax obligations, and submission requirements still need human review.

## Quick start

Python 3.11 or newer is required.

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
money-agent run --per-query 20 --top 5
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

The default heuristic evaluator makes no paid model calls. Evaluations are cached by opportunity content hash, evaluator, and model name.

## Safety boundary

v0.1 only reads public opportunity data and writes to a local SQLite database. It does not:

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

Opportunity score is a 0–100 prioritization score combining expected profit, automation potential, success probability, difficulty, competition, platform risk, and estimated time. The v0.1 coefficients are provisional and should be recalibrated from real outcomes.

## Development

```bash
pytest
ruff check .
```

## Roadmap

1. Add fixture-backed integration tests and resilient GitHub rate-limit handling.
2. Add a Freelancer collector only after confirming current official API access and terms.
3. Add cheap/strong model routing with token and dollar budgets.
4. Add an approval inbox before any external submission capability.
5. Add a sandboxed coding worker and an independent verifier.
