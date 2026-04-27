# refactor: move daily_log_today from ContextSchema to AgentState via load_daily_context node

**Date**: 2026-04-26
**Branch**: daily_log_loader
**Commit**: 93c2d2d
**ADRs**: [ADR-0002](../docs/adr/0002-daily-log-loader-node-into-state.md) (superseded) → [ADR-0003](../docs/adr/0003-daily-log-loader-before-response.md) (accepted)
**Plans**: [original](../docs/plans/daily-log-loader-node-into-state.md) (entry + post-commit) → [final](../docs/plans/daily-log-loader-before-response.md) (loader-before-response)
**Bug audit**: LangSmith thread `73ed31fb-8391-4c97-a05f-a4b672c6fcd5` (2026-04-22)

## What changed

### The bug
After a HITL confirm-and-commit turn, `response_node` reported wrong daily summaries (e.g. "4 protein / 2 carbs" instead of the correct "5.6 / 5"). Root cause: the gateway snapshotted `daily_log_today` into `runtime.context` *before* the request, `commit_node` wrote new `daily_logs` rows *during* the request, but `runtime.context` is request-scoped and immutable from inside the graph — so `response_node` read the stale snapshot.

### The fix
- `daily_log_today` removed from `ContextSchema`, moved to `AgentState`.
- New node `load_daily_context` in `src/agents/nodes/load_daily_context_node.py` fetches today's log via `get_todays_logs_serialized` and writes to state.
- Graph topology rewired so the loader sits as the **single hop before `response_node`** on every path. Five rewires:
  1. `route_parser` default `"response"` → `"load_daily_context"`
  2. `route_after_selection` default `"response"` → `"load_daily_context"`
  3. `commit → response` direct edge → `commit → load_daily_context`
  4. `personal_stats → response` direct edge → `personal_stats → load_daily_context`
  5. `stats_lookup → response` direct edge → `stats_lookup → load_daily_context`
- One new edge: `load_daily_context → response`.
- `confirmation_node`'s two `Command(goto="response")` paths rewired to `goto="load_daily_context"`.
- `bot/gateway.py` stops fetching the daily log entirely (gateway shrinks to identity + `user_profile`).

### The invariant now in force
**Nothing reaches `response` without passing through `load_daily_context` first.** `daily_log_today` is fresh by construction at every read.

## Architecture journey

This change went through **two ADRs**:

1. **ADR-0002 (initial decision)** placed the loader at graph entry + after `commit_node` with a conditional edge dispatching on `last_action`. The motivation was forward-compat for hypothetical mid-graph consumers (a coaching node, plan-aware estimation in `calculate_macros_node`, an end-of-day summary node).

2. **ADR-0003 (chosen, supersedes 0002)** simplified to "loader only before response_node" after the user pushed back during planning: *if today the only consumer is `response_node`, why pay topology cost for hypothetical consumers?* When a real mid-graph consumer arrives, adding a loader edge for it is the same single-edge change either way. YAGNI applied correctly.

The implementation execution (Tasks 1–15 + 17 of the plan) ran clean. Two minor deviations:
- `tests/unit/test_confirmation_node.py` had two assertions on `goto="response"` that needed rewiring (not anticipated in plan; caught by unit suite).
- The loader needed a `runtime.context is None` defensive guard (mirrors `response_node:210`) for invocations without context (Studio, some tests).

## Files

### New
- `src/agents/nodes/load_daily_context_node.py` — the loader node (~28 LOC).
- `tests/unit/test_load_daily_context_node.py` — 3 unit tests for the loader.
- `docs/adr/0002-daily-log-loader-node-into-state.md` — initial ADR (now superseded but kept as immutable record per ADR skill rules).
- `docs/adr/0003-daily-log-loader-before-response.md` — chosen ADR, supersedes 0002.
- `docs/plans/daily-log-loader-node-into-state.md` — original implementation plan (entry + post-commit topology). Historical.
- `docs/plans/daily-log-loader-before-response.md` — final implementation plan (the one executed).

### Modified
- `src/agents/state.py` — `daily_log_today: List[dict]` added to `AgentState`.
- `src/context.py` — `daily_log_today` field removed from `ContextSchema`.
- `src/agents/nutritionist.py` — node registered, 5 edge/route rewires, 1 new edge.
- `src/agents/nodes/response_node.py` — reads `state["daily_log_today"]`.
- `src/agents/nodes/confirmation_node.py` — both `Command(goto="response")` rewired.
- `bot/gateway.py` — `_load_todays_log` helper removed, kwarg removed, body injection removed, import removed, both call-site kwargs removed.
- `docs/adr/DECISIONS.md` — ADR-0002 marked superseded; ADR-0003 entry appended.
- `docs/patterns/runtime-context.md` — new "What Belongs in Context vs State" carve-out section.
- `tests/conftest.py` — `daily_log_today: []` added to `basic_state` fixture.
- `tests/unit/test_response_node.py` — `_make_state` default + 2 tests rewired (state, not context).
- `tests/unit/test_gateway.py` — 6 mock decorators + parameters + assertions removed.
- `tests/unit/test_feedback_integration.py` — `mock_loader` patch added.
- `tests/unit/test_confirmation_node.py` — 2 assertions rewired.

## Validation

- `uv run ruff check` (13 files): **passed**
- `uv run pytest tests/unit/`: **155 passed** (was 153 before; +3 from new loader tests, but 2 confirmation_node tests rewired in place — net +2 visible)
- `uv run pytest tests/integration/`: **45 passed** (385s)
- `uv run pytest tests/graph_api/`: **13 passed** (98s)

## Resolves

- ADR-0002 / ADR-0003 (this is their implementation)
- Staleness bug from LangSmith thread `73ed31fb-…`

## Next steps

- **Manual smoke** (Task 16 from the plan): run bot locally with `POLLING_MODE=true`, log a multi-item food list, confirm with "yes", immediately ask "where am I today?" — summary should reflect the just-confirmed items. *Not yet run.*
- **CLAUDE.md sync**: the `Runtime Context + User Profile` row currently says `ContextSchema` includes `daily_log_today`. Run `sync-context` (or update by hand) to reflect that it now lives in `AgentState`.
- **Continue the bot-conversation audit**: the user has more LangSmith threads to walk through. This one (the 2026-04-22 staleness bug) was the first.

## Out of scope / known follow-ups

- **Bug 1 (UTC date boundary)** — `get_todays_logs_serialized` still inherits the `func.date()` UTC-vs-Israel boundary issue from `get_logs_by_date`. Logs made 00:00–03:00 Israel local fall on the previous UTC date and are missed. Pre-existing; tracked in `brain/TASKS.md`.
- **Conversation backup** — `brain/conversations_beckups/2026-04-25_daily-log-loader-node-into-state.md` was exported during the planning conversation. Both ADR-0002 and ADR-0003 reference it; no second backup needed.
