# Refactor: Sync Nodes to Async + Module-Level Prompt Loading

**Date:** 2026-04-06
**Branch:** Menu-and-Personal-Details
**Commits:**
- `202cc0c` — refactor: convert sync nodes to async and move prompt loading to module level
- `cda52ba` — docs: add state-schemas and async-patterns context files, refactor plan

## Summary

Eliminated the last sync code from the LangGraph runtime path. Three nodes were still using `def` + `llm.invoke()` while everything else was async — this refactor makes the entire graph consistently async and moves all prompt file I/O to import time.

## Changes Implemented

### Sync → Async Node Conversion (3 nodes)

Converted from `def` + `llm.invoke()` to `async def` + `await llm.ainvoke()`:

- `src/agents/nodes/input_node.py`
- `src/agents/nodes/selection_node.py`
- `src/agents/nodes/response_node.py`

### Module-Level Prompt Loading (6 nodes)

Moved prompt file reads from runtime `open()` calls to module-level `_SYSTEM_PROMPT` / `_ESTIMATION_PROMPT` / `_CONFIRMATION_PROMPT` constants. Prompts are now loaded once at import time, eliminating sync file I/O from graph execution:

- `src/agents/nodes/input_node.py`
- `src/agents/nodes/selection_node.py`
- `src/agents/nodes/response_node.py`
- `src/agents/nodes/calculate_macros_node.py` (inside `_estimate_macros`)
- `src/agents/nodes/confirmation_node.py` (inside `_parse_confirmation`, kept runtime `.replace("{batch_context}", ...)`)
- `src/agents/nodes/personal_stats_node.py`

### Test Updates (5 files)

Converted sync tests to async with `AsyncMock` replacing sync `MagicMock.invoke`:

- `tests/unit/test_input_parser.py`
- `tests/unit/test_agent_selection.py`
- `tests/unit/test_response_node.py`
- `tests/unit/test_feedback_logic.py`
- `tests/unit/test_feedback_integration.py`

### Documentation Added

- `.claude/patterns/state-schemas.md` — InputState/AgentState/OutputState tier model, field-name duck typing, reducer rules
- `.claude/patterns/async-patterns.md` — fully-async runtime, DB engine setup, SSL workaround, prompt loading rules, known gotchas
- `.agent/plans/refactor-sync-nodes-to-async.md` — implementation plan that drove this refactor

## Validation Results

| Suite | Result |
|---|---|
| `ruff check .` | ✅ All checks passed |
| Unit tests (95) | ✅ All passed |
| Graph-API E2E tests (13) | ✅ All passed (full server + real LLM, 4 minutes) |
| Integration tests | ⚠️ Hung on pre-existing DB connection pool issue (fixture creates engine per test, exhausts Supabase pool). Not related to this refactor. |

## Next Steps

1. **Fix integration test fixture** — scope `create_async_engine` to session/module level instead of per-test to prevent connection pool exhaustion.
2. **Continue pattern files** — 8 more architecture pattern files still need to be created in `.claude/patterns/`:
   - `tool-first.md`, `llm-config.md`, `hitl-confirmation.md`, `off-menu-estimation.md`, `schema-management.md`, `auth-and-users.md`, `bot-gateway.md`, `data-flow.md`
