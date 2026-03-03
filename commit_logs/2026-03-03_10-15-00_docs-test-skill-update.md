# Docs: Update Test-Engineering Skill & Fix Stale Server References

**Commit**: `e8d90a2`
**Branch**: `main`
**Date**: 2026-03-03

## Summary

Fixed outdated documentation across 7 files. Two categories of changes:

### 1. Server Auto-Start References (6 files)
All references to "requires: uv run langgraph dev" replaced with "server auto-starts via conftest". The `tests/graph_api/conftest.py` has handled server lifecycle automatically since commit `30ad995`, but docs still said manual startup was needed.

### 2. Test-Engineering Skill Accuracy (3 files)

**`fitpal-test-strategy.md`**:
- Section 4.1: Renamed "Always Mock in Unit Tests" → "Always Mock in **Node** Unit Tests". Removed stale DB session and service layer mock patterns (nodes no longer import those).
- Section 4.2: New — "Never Mock in **Service** Unit Tests" documenting the DI + `async_test_db_session` pattern.
- Section 7: Added Pattern column to decision matrix mapping each scenario to one of three test patterns.

**`unit-testing.md`**:
- Section 6: New — "Testing Service Functions (Real DB, Zero Mocks)" with example code.

**`graph-api-testing.md`**:
- Full rewrite — removed manual server instructions, documented auto-start conftest with fixture table.

## Files Changed
- `CLAUDE.md`
- `tests/graph_api/conftest.py` (docstring only)
- `.claude/skills/test-engineering/SKILL.md`
- `.claude/skills/test-engineering/references/fitpal-test-strategy.md`
- `.claude/skills/test-engineering/references/graph-api-testing.md`
- `.claude/skills/test-engineering/references/unit-testing.md`
- `.claude/skills/validation/SKILL.md`
