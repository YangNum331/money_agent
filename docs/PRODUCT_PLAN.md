# Product plan

## Goal

Build a local-first, semi-automated micro-business system that discovers legitimate paid technical work, estimates value and risk, performs selected work in a constrained sandbox, verifies the result, and waits for explicit human approval before any submission.

## Release sequence

### v0.1 — discover and rank

- GitHub and, after API/terms validation, Freelancer collection
- normalized opportunity records in SQLite
- deterministic pre-filtering and deduplication
- cheap and strong evaluator routing
- expected-profit ranking and CLI output

No external writes or third-party code execution are allowed.

### v0.2 — work and verify

- resource-limited task sandbox
- coding worker
- independent verifier
- reproducible result package: diff, test output, cost, assumptions, unresolved risk

### v0.3 — approve

- local approval inbox
- bid, PR, and customer-message drafts
- immutable audit trail for every approval or rejection

### v0.4 — submit and measure

- platform integrations that comply with current terms
- human-triggered submission
- outcome, fee, API-cost, and profit recording

### v1.0 — improve allocation

- scheduled discovery
- measured profit per API dollar and per human minute
- statistics-based strategy updates from real outcomes

## Non-goals

No CAPTCHA bypass, account farming, spam applications, fake identities, hidden contracting, automatic payments, or credential exposure. Opportunity volume is not success; realized risk-adjusted profit is.

