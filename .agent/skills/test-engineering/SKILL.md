---
name: test-engineering
description: FitPal-specific testing engineering skill. Covers how to write, structure, and run tests for the FitPal LangGraph agent. Use when writing any test (unit, integration, or graph-api), when a test fails unexpectedly, when adding a new node/route/schema, or when setting up a new test file. Provides mock boundary rules, file structure conventions, AAA docstring standards, and graph-api end-to-end testing patterns using langgraph-sdk.
---

# Test Engineering — FitPal

## Reference Files

Load the relevant file based on the task:

| Task | Read |
|---|---|
| Writing or fixing a unit test | [fitpal-test-strategy.md](references/fitpal-test-strategy.md) + [unit-testing.md](references/unit-testing.md) |
| Setting up a new test file from scratch | [unit-testing.md](references/unit-testing.md) |
| Writing or fixing an end-to-end graph flow test | [fitpal-test-strategy.md](references/fitpal-test-strategy.md) + [graph-api-testing.md](references/graph-api-testing.md) |
| Unsure which tier a test belongs to | [fitpal-test-strategy.md](references/fitpal-test-strategy.md) |
| A test fails that shouldn't | [fitpal-test-strategy.md](references/fitpal-test-strategy.md) (mock boundary rules) |

> Read ONLY the files relevant to the current task to avoid loading unnecessary context.

## Test Tier Decision

```
Does the test mock any I/O (LLM, DB)?
  YES → tests/unit/
  NO, but tests compilation/DB/LLM directly → tests/integration/
  NO, tests the full graph through the HTTP API runtime → tests/graph_api/
```

## Validation Commands

```bash
# Pre-commit gate (mandatory, fast ~15s)
uv run pytest tests/unit/ -v

# After schema or prompt changes
uv run pytest tests/ -v

# Graph-api suite (requires langgraph dev running)
uv run pytest tests/graph_api/ -v -s

# Single file during development
uv run pytest tests/unit/test_<specific>.py -v

# Last-failed retry loop
uv run pytest --lf -v
```
