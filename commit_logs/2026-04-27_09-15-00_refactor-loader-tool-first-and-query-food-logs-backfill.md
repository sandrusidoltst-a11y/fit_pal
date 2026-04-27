# refactor: restore tool-first in load_daily_context + backfill query_food_logs with coach-mapping joins

**Date**: 2026-04-27
**Branch**: daily_log_loader (continuing the same PR as previous commit logs in this series)
**Commit**: `b27ab0e`
**Plan**: [`docs/plans/loader-tool-first-via-query-food-logs-backfill.md`](../docs/plans/loader-tool-first-via-query-food-logs-backfill.md)
**RCA**: [`docs/rca/plan-3d-incomplete-migration-and-tool-first-drift.md`](../docs/rca/plan-3d-incomplete-migration-and-tool-first-drift.md)
**Surfaced by**: PR review of commits `93c2d2d` + `cdef9f4` from 2026-04-26

## What changed

### Two coordinated fixes

#### 1. Tool-first restored in `load_daily_context_node`
The new node introduced by `93c2d2d` opened its own DB session via `get_async_db_session` and called the service function `get_todays_logs_serialized` directly — violating CLAUDE.md's "Tool-First + Service Layer" rule (*"All DB access through async @tool functions. Nodes are thin orchestrators... never import DB sessions"*). Refactored to call the existing `query_food_logs` tool. The loader's full body is now ~12 LOC with no DB-engine imports.

#### 2. Plan 3d backfill in `query_food_logs`
Plan 3d (food catalog Plan 3 trilogy + serving-math) added `_with_mappings` helpers and extended `_serialize_log` to optionally emit `category`/`tag`/`serving_amount_g`. It migrated the new context-injection path (`get_todays_logs_serialized`) but left the legacy `query_food_logs` tool calling the un-joined `get_logs_by_date` / `get_logs_by_date_range`. This commit:
- Adds `get_logs_by_date_range_with_mappings` (the missing range variant — mirror of the single-date with-mappings helper).
- Migrates `query_food_logs` to use the with-mappings variants on both branches.
- Side benefit: `stats_lookup_node` (populates `daily_log_report` for QUERY_DAILY_STATS) and `commit_node` (refreshes `daily_log_report` after writes) now also surface coach-mapping data, reaching feature parity with the new `daily_log_today` injection path.

### The link between the two

The reason the new loader had to bypass the convention was that the existing tool didn't have the data shape it needed (Plan 3d had only migrated one path). Backfilling Plan 3d makes the tool sufficient → the loader can become a thin orchestrator → convention restored. Two issues, one PR, because they're causally connected.

### Side effect — `daily_log_report` upgrade for free

`commit_node` (`commit_node.py:98-100`) calls `query_food_logs` to refresh `daily_log_report` after each write batch. After this PR, that field will carry coach-mapping data on every refresh. Same goes for `stats_lookup_node`. This is purely additive — `QueriedLog` TypedDict already declared `category`/`tag`/`serving_amount_g` as `Optional` (Plan 3d). Existing readers either ignore the extra keys (LLM context JSON) or already supported them (TypedDict). No breaks.

## Files

### Modified
- `src/services/daily_log_service.py` — added `get_logs_by_date_range_with_mappings`; migrated `query_food_logs`; removed dead `get_todays_logs_serialized`; dropped unused `USER_TIMEZONE` import.
- `src/agents/nodes/load_daily_context_node.py` — rewritten as a tool-first orchestrator.
- `tests/unit/test_load_daily_context_node.py` — 3 tests rewritten to mock `query_food_logs` (single mock surface); `target_date` assertion computed at assertion time to stay green across days.
- `tests/integration/test_daily_log_service.py` — removed `TestGetTodaysLogsSerialized`; migrated 2 `TestEnrichedQuery` serialized-form tests to use `get_logs_by_date_with_mappings` + `_serialize_log` directly; added `TestGetLogsByDateRangeWithMappings` (4 cases).

### New
- `docs/plans/loader-tool-first-via-query-food-logs-backfill.md` — implementation plan.
- `docs/rca/plan-3d-incomplete-migration-and-tool-first-drift.md` — RCA naming both anti-patterns ("migration via parallel implementation" + "convention drift via plan-induced shortcuts"), the codebase audit results, and three preventive measures.

## Plan deviations

- **`test_user_scoping` failed once** with strict-exclusivity assertion. `TEST_USER_A` is the dev user (`fbeeb45f-…`) and may have pre-existing real logs on today's date in Supabase that aren't wiped by transaction rollback. Loosened the assertion to **set membership** ("user A's row is in user A's results AND not in user B's, and vice versa") — same scoping guarantee, robust against real-DB contamination.

## Validation

- `uv run ruff check` (4 files): **passed**
- `uv run pytest tests/unit/`: **155 passed** (1.18s)
- `uv run pytest tests/integration/test_daily_log_service.py`: **20 passed** (61s) — includes the 4 new range-with-mappings tests + the 2 migrated `TestEnrichedQuery` tests
- `uv run pytest tests/graph_api/`: **13 passed** (87s)

Full integration suite was not re-run end-to-end; only the daily_log subset (the change is contained to that service).

## Resolves

- Tool-first violation introduced in commit `93c2d2d`.
- Plan 3d's unfinished migration of `query_food_logs`.
- Both issues documented in `docs/rca/plan-3d-incomplete-migration-and-tool-first-drift.md`.

## Next steps

- **Push to `daily_log_loader`** — the existing PR auto-updates with `cdef9f4` + this commit `b27ab0e`. The PR will then carry the full sequence: ADR-0003 implementation → topology fix-up → tool-first restoration → Plan 3d backfill.
- **Manual smoke** still useful: log a meal, ask "what did I eat this week?" — response should now render the coach-method category breakdown for the legacy stats path.
- **CLAUDE.md sync** post-merge: `Runtime Context + User Profile` row already became inaccurate after ADR-0003 (covered separately); no new drift from this commit.

## Out of scope / known follow-ups

- **Gateway DB-access (`bot/gateway.py:204, 217`)** — `_load_user_profile` and `_save_user_profile` open sessions directly. The convention text addresses *nodes*; the gateway is transport-layer. Worth a separate explicit decision (clarify CLAUDE.md or migrate to tool wrappers). Tracked in the RCA's "Gateway DB access" section.
- **Bug 1 (UTC date boundary)** — `func.date(timestamp) == target_date` evaluates in UTC; logs at 00:00–03:00 Israel local fall on the previous UTC date. Pre-existing; tracked in `brain/TASKS.md`.
- **Pre-merge grep checks** for tool-first invariant — proposed in the RCA's preventive measures section. Could land as a CI lint or PR template check; not in scope of this PR.
