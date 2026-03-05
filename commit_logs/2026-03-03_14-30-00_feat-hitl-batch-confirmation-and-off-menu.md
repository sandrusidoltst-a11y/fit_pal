# feat: HITL Batch Confirmation Gate + Off-Menu Macro Estimation

**Date**: 2026-03-03
**Branch**: `HITL_and_off_menu`
**Commit**: `e40b06b`

## Summary

Split the monolithic `calculate_log_node` (which calculated macros AND wrote to DB in one step) into three specialized nodes with a human-in-the-loop confirmation gate:

1. **`calculate_macros_node`** — Preview-only macro calculation (DB lookup or LLM estimation)
2. **`confirmation_node`** — HITL batch confirmation using LangGraph's `interrupt()` in a validation loop
3. **`commit_node`** — Batch DB write after user confirms

Added off-menu fallback: when food is not found in the database, LLM estimates macros tagged with `source: "estimated"` for transparency.

## Files Created
- `src/agents/nodes/calculate_macros_node.py` — Macro calc (DB or estimation path)
- `src/agents/nodes/confirmation_node.py` — HITL interrupt loop with confirm/reject/edit
- `src/agents/nodes/commit_node.py` — Batch DB write
- `src/schemas/estimation_schema.py` — `MacroEstimation` Pydantic schema
- `src/schemas/confirmation_schema.py` — `ConfirmationResponse` + `ItemEdit`
- `prompts/macro_estimation.md` — Off-menu estimation prompt
- `prompts/confirmation_parser.md` — Confirmation response parser prompt
- `tests/unit/test_calculate_macros_node.py` — 6 tests
- `tests/unit/test_confirmation_node.py` — 7 tests
- `tests/unit/test_commit_node.py` — 5 tests

## Files Modified
- `src/agents/state.py` — Added `MacroResult`, `pending_confirmations`, new `GraphAction` literals
- `src/agents/nutritionist.py` — Rewired graph with 3 new nodes, `Command`-based routing
- `src/agents/nodes/selection_node.py` — Simplified NO_MATCH (estimation handles it)
- `src/agents/nodes/response_node.py` — Added CONFIRMED/REJECTED to context builder
- `src/models.py` — `DailyLog.food_id` now nullable for estimated items
- `src/services/daily_log_service.py` — `food_id` accepts `Optional[int]`
- `src/config.py` — Added `estimation_node` and `confirmation_node` configs
- `CLAUDE.md` — Updated structure, architecture patterns, reference table
- `PRD.md` — Updated mermaid diagram, node table, state schema

## Files Deleted
- `src/agents/nodes/calculate_log_node.py` — Split into 3 new nodes
- `tests/unit/test_calculate_log_node.py` — Replaced by new test files

## Test Results
- **68 unit tests** — all passing
- **2 graph compilation tests** — all passing

## Next Steps
- [ ] Run `tests/graph_api/test_graph_flows.py` E2E tests (requires langgraph dev server)
- [ ] Manual Studio testing: confirm/reject/edit flows with `langgraph dev`
- [ ] Create PR after Studio validation passes
- [ ] Consider wrapping LLM calls in `@task` for interrupt replay idempotency (future)
