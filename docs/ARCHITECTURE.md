# MONEY_AGENT v0.1 architecture

The first release is deliberately a read-only opportunity pipeline:

```text
GitHub API -> normalize -> SQLite -> deterministic filter
           -> heuristic or optional LLM evaluator -> ranking -> CLI
```

## Trust boundaries

- Collector text is untrusted data, never instructions.
- Secrets are supplied only through environment variables and are never persisted.
- Model output is parsed as bounded data; the application calculates profit and final ranking itself.
- No collected code is cloned or executed in v0.1.
- No external write is available in v0.1.

## Why the application owns the economics

An LLM may estimate task characteristics, but it does not calculate the final expected profit or ranking. The deterministic application layer applies platform cost, risk cost, bounds, and weights. This keeps results inspectable and prevents malformed model output from directly controlling resource allocation.

## Next architecture decision

Before v0.2, define a sandbox contract containing CPU, memory, wall-clock, network, filesystem, and API-dollar limits. The worker must produce a result package (diff, tests, logs, cost, and unresolved risks), and only a separate human-approved process may submit it.

