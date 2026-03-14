---
name: test-engineering
description: FitPal-specific testing engineering skill. Covers how to write, structure, and run tests for the FitPal LangGraph agent. Use when writing any test (unit, integration, or graph-api), when a test fails unexpectedly, when adding a new node/route/schema, or when setting up a new test file. Provides mock boundary rules, file structure conventions, AAA docstring standards, integration DB testing patterns, and graph-api end-to-end testing patterns using langgraph-sdk.
---

# Test Engineering — FitPal

## Reference Files

Load the relevant file based on the task:

| Task | Read |
|---|---|
| Writing or fixing a unit test | [fitpal-test-strategy.md](references/fitpal-test-strategy.md) + [unit-testing.md](references/unit-testing.md) |
| Writing or fixing an integration test (real DB) | [fitpal-test-strategy.md](references/fitpal-test-strategy.md) + [integration-testing.md](references/integration-testing.md) |
| Setting up a new unit test file from scratch | [unit-testing.md](references/unit-testing.md) |
| Setting up a new integration test file from scratch | [integration-testing.md](references/integration-testing.md) |
| Writing or fixing an end-to-end graph flow test | [fitpal-test-strategy.md](references/fitpal-test-strategy.md) + [graph-api-testing.md](references/graph-api-testing.md) |
| Unsure which tier a test belongs to | [fitpal-test-strategy.md](references/fitpal-test-strategy.md) |
| A test fails that shouldn't | [fitpal-test-strategy.md](references/fitpal-test-strategy.md) (mock boundary rules) |

> Read ONLY the files relevant to the current task to avoid loading unnecessary context.

## Test Tier Decision

```
Does the test mock ALL I/O (LLM, DB, tools)?
  YES → tests/unit/
  NO  → Does it need the real DB but NOT the LangGraph server?
    YES → tests/integration/
    NO  → tests/graph_api/
```

## Validation Commands

```bash
# Pre-commit gate (mandatory, fast ~15s, offline)
uv run pytest tests/unit/ -v

# Integration — real Supabase DB (service layer, models, tool scoping)
uv run pytest tests/integration/ -v

# Graph-api suite (server auto-starts via conftest)
uv run pytest tests/graph_api/ -v -s

# After schema or prompt changes (all tiers)
uv run pytest tests/ -v -s

# Single file during development
uv run pytest tests/unit/test_<specific>.py -v

# Last-failed retry loop
uv run pytest --lf -v
```
