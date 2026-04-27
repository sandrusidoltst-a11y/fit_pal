# Feature: Restore tool-first in `load_daily_context` by backfilling `query_food_logs` with coach-mapping joins

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files.

> **Why this plan exists**: PR review of the ADR-0003 implementation (`commit_logs/2026-04-26_09-40-00_refactor-daily-log-loader-before-response.md`) surfaced two related issues. (1) `load_daily_context_node.py` opens its own DB session via `get_async_db_session`, violating the project's tool-first convention from CLAUDE.md ("All DB access through async @tool functions. Nodes are thin orchestrators via `await tool.ainvoke(...)` — never import DB sessions."). (2) The reason the new node *had* to bypass the convention is that the existing `query_food_logs` tool doesn't include the coach-mapping join — the join was added in Plan 3d for a single helper function (`get_logs_by_date_with_mappings`) and the legacy tool was never backfilled. Both issues land naturally in one PR because the cleanest fix for (1) is to make (2) go away first.

## Feature Description

Two coordinated changes:

1. **Backfill `query_food_logs`** to always join `coach_food_mappings` and emit category/tag/serving_amount_g — completing Plan 3d's unfinished migration. Both the single-date branch and the range branch are migrated; this requires adding a new helper `get_logs_by_date_range_with_mappings` (mirror of the existing `get_logs_by_date_with_mappings`).
2. **Rewire `load_daily_context_node`** to call the tool (`query_food_logs.ainvoke({"target_date": today_iso, "user_id": user_id})`) instead of importing `get_async_db_session` and calling the service function directly. The loader computes "today in Israel" itself (one line) and passes it explicitly — no implicit defaults in the tool.

After this change, `get_todays_logs_serialized` (the service-layer helper used only by the previous loader implementation) becomes dead code and is removed.

## User Story

As **Dolev (the developer)**,
I want every node in the FitPal graph to access the database only through `@tool` functions,
So that the codebase keeps its single architectural convention and reviewers don't see a node opening its own session.

As a **trainee**,
I want the bot's daily-log section in any view (today's snapshot, post-commit refresh, stats query for an arbitrary date) to render the coach-method category breakdown,
So that the LLM can reason about my budget remaining without me having to teach it the per-category math each time.

## Problem Statement

Two compounding problems:

1. **Tool-first violation in `load_daily_context_node.py`** — the node calls `get_async_db_session()` directly. CLAUDE.md's "Tool-First + Service Layer" rule is explicit that nodes should never do this. Reviewing the PR caught this immediately.
2. **`query_food_logs` is missing a piece of Plan 3d** — Plan 3d (food catalog Plan 3, commit `b562262` and following) added `get_logs_by_date_with_mappings` and extended `_serialize_log` to accept an optional `mapping` arg. But only the new context-injection helper (`get_todays_logs_serialized`) was migrated to use the with-mappings variant. The legacy `query_food_logs` tool — which serves `stats_lookup_node` (populating `daily_log_report` for QUERY_DAILY_STATS) and `commit_node` (refreshing `daily_log_report` after writes) — still uses the un-joined `get_logs_by_date` / `get_logs_by_date_range`. Result: any view of historical or arbitrary-date logs is missing the coach-method category metadata, so the LLM can't render the per-category totals block.

The link between (1) and (2): the only reason the new loader had to call a service function instead of a tool was that the existing tool didn't have the data shape we needed. Backfill (2), and (1) becomes trivially fixable.

## Solution Statement

1. Add `get_logs_by_date_range_with_mappings` (`src/services/daily_log_service.py`) — mirror of `get_logs_by_date_with_mappings` for the range case. ~15 LOC.
2. Migrate `query_food_logs` to use `get_logs_by_date_with_mappings` (single-date) and `get_logs_by_date_range_with_mappings` (range). The serializer call becomes `_serialize_log(log, mapping)` for tuple iteration. The tool's *return shape grows* — every dict now optionally carries `category`, `tag`, `serving_amount_g` (already present when mapping exists; absent when no mapping). This is purely additive; existing assertions like `assert log["protein"] == 31` still pass.
3. Refactor `load_daily_context` (`src/agents/nodes/load_daily_context_node.py`) — remove the `get_async_db_session` and `get_todays_logs_serialized` imports; compute `today_iso = datetime.now(USER_TIMEZONE).date().isoformat()`; call `await query_food_logs.ainvoke({"target_date": today_iso, "user_id": user_id})`.
4. Delete `get_todays_logs_serialized` from `src/services/daily_log_service.py` — only the loader called it, and the loader no longer does. Also delete the corresponding `TestGetTodaysLogsSerialized` tests in `tests/integration/test_daily_log_service.py` (the loader's behavior is now covered by `query_food_logs`'s tests; the loader's own unit tests cover the date-computation seam).
5. Update `tests/unit/test_load_daily_context_node.py` to mock `query_food_logs` directly (instead of `get_todays_logs_serialized` + `get_async_db_session`).
6. Add an integration test `TestGetLogsByDateRangeWithMappings` in `tests/integration/test_daily_log_service.py` covering the new helper.
7. Verify existing `query_food_logs` integration tests still pass — the change is additive, so all current assertions hold; optionally extend tests to assert the new fields are present when mappings exist.

## Feature Metadata

**Feature Type**: Refactor (architectural — tool-first compliance) + Bug Fix (Plan 3d migration backfill)
**Estimated Complexity**: Low–Medium
**Primary Systems Affected**:
- `src/services/daily_log_service.py` (new helper, `query_food_logs` migration, `get_todays_logs_serialized` deletion)
- `src/agents/nodes/load_daily_context_node.py` (tool call rewire)
- Tests: `tests/unit/test_load_daily_context_node.py`, `tests/integration/test_daily_log_service.py`

**Dependencies**: None new. `_serialize_log(log, mapping)` already handles the optional-mapping shape (Plan 3d). `get_logs_by_date_with_mappings` is the template for the new range variant. `USER_TIMEZONE`, `date`, `datetime` are already imported elsewhere in the loader's neighbors.

**Resolves**:
- Tool-first convention violation introduced in commit `93c2d2d` (this PR's first commit)
- Plan 3d backfill gap in `query_food_logs` — `stats_lookup` and `commit_node` refresh paths now carry coach-mapping data

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `CLAUDE.md` — Architecture Patterns table, "Tool-First + Service Layer" row. The convention this plan restores.
- `docs/patterns/tool-first.md` (full file) — the canonical pattern doc for tool-first. Confirms nodes never import DB sessions; service functions accept `session` for DI; `@tool` wrappers own their session.
- `docs/adr/0003-daily-log-loader-before-response.md` — the immediately-preceding ADR. This plan does not change ADR-0003's decision; it just restores the tool-first compliance the previous plan failed to require.
- `commit_logs/2026-04-26_09-40-00_refactor-daily-log-loader-before-response.md` — the ADR-0003 commit log. Names the loader and the convention it should follow (this plan brings it into compliance).
- `src/services/daily_log_service.py` (full file, 288 lines) — central file for this plan:
  - Lines 109-129: `get_logs_by_date` (legacy, no mappings)
  - Lines 132-159: `get_logs_by_date_with_mappings` (Plan 3d) — **the template for the new range helper**
  - Lines 162-186: `get_logs_by_date_range` (legacy, no mappings)
  - Lines 193-225: `_serialize_log(log, mapping=None)` — already handles optional mapping; no change needed here
  - Lines 228-243: `get_todays_logs_serialized` — **deleted by this plan** (was only called by the old loader implementation)
  - Lines 277-288: `query_food_logs` tool — **migrated to use with-mappings variants on both branches**
- `src/agents/nodes/load_daily_context_node.py` (full file, ~28 LOC after the previous PR) — the loader. Imports to remove: `get_async_db_session`, `get_todays_logs_serialized`. Imports to add: `query_food_logs`, `USER_TIMEZONE`, `date`/`datetime` (whichever is needed for the today-in-Israel computation).
- `src/agents/nodes/commit_node.py` (full file, 109 lines) — already imports and calls `query_food_logs` (line 98-100) to refresh `daily_log_report` after writes. Body unchanged by this plan; `daily_log_report` will simply gain the new optional fields automatically.
- `src/agents/nodes/stats_node.py` (full file, 37 lines) — calls `query_food_logs` to populate `daily_log_report`. Body unchanged; output shape grows.
- `src/agents/state.py` (lines 38-56 specifically) — `QueriedLog` TypedDict already includes `category`, `tag`, `serving_amount_g` as `Optional`. So the state shape already supports the new fields; the migration only fills in values that were always typed as possible.
- `src/config.py` — `USER_TIMEZONE = ZoneInfo("Asia/Jerusalem")` already exists. Import from here, do not redefine.
- `tests/integration/test_daily_log_service.py` (full file) — find `TestGetTodaysLogsSerialized` and the `query_food_logs` test classes. The former is removed; the latter need to keep passing (they will, since change is additive) and ideally extended to cover the new fields.
- `tests/unit/test_load_daily_context_node.py` (full file, 3 tests) — currently mocks `get_todays_logs_serialized` + `get_async_db_session`. Will be rewritten to mock `query_food_logs.ainvoke`.

### New files to create

None. All changes are edits or in-file additions.

### Files removed (functions, not files)

- `get_todays_logs_serialized` function in `src/services/daily_log_service.py` — dead after the loader's tool call replaces it.
- `TestGetTodaysLogsSerialized` test class in `tests/integration/test_daily_log_service.py` — covers a function that no longer exists.

### Relevant Documentation — YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [LangChain `@tool` decorator](https://python.langchain.com/docs/concepts/tools/) — confirms that `@tool`-wrapped async functions can be called via `.ainvoke({"key": value})` from anywhere, including graph nodes.
  - Why: this is exactly what the loader will do.
- (Use the `docs-langchain` MCP server if any signature ambiguity arises.)

### Patterns to Follow

**Service helper pattern** (mirror `src/services/daily_log_service.py:132-159`):
```python
async def get_logs_by_date_range_with_mappings(
    session: AsyncSession,
    user_id: str,
    start_date: date,
    end_date: date,
    coach_id: uuid_mod.UUID = DEFAULT_COACH_ID,
) -> List[Tuple[DailyLog, Optional[CoachFoodMapping]]]:
    """Range version of get_logs_by_date_with_mappings — see that fn for shape."""
    stmt = (
        select(DailyLog, CoachFoodMapping)
        .outerjoin(
            CoachFoodMapping,
            (CoachFoodMapping.food_id == DailyLog.food_id)
            & (CoachFoodMapping.coach_id == coach_id),
        )
        .where(
            DailyLog.user_id == uuid_mod.UUID(user_id),
            func.date(DailyLog.timestamp) >= start_date,
            func.date(DailyLog.timestamp) <= end_date,
        )
        .order_by(DailyLog.timestamp)
    )
    rows = (await session.execute(stmt)).all()
    return [(r[0], r[1]) for r in rows]
```

**Tool migration pattern** — `query_food_logs` becomes:
```python
@tool
async def query_food_logs(target_date: str, end_date: str = "", user_id: str = "") -> list[dict]:
    """Query food log entries by date or date range. Dates ISO format (YYYY-MM-DD).
    Returns serialized log dicts including coach-method category/tag/serving_amount_g
    when the food has a mapping for the default coach.
    """
    parsed_date = date.fromisoformat(target_date)
    async with get_async_db_session() as session:
        if end_date:
            parsed_end = date.fromisoformat(end_date)
            rows = await get_logs_by_date_range_with_mappings(session, user_id, parsed_date, parsed_end)
        else:
            rows = await get_logs_by_date_with_mappings(session, user_id, parsed_date)
        logger.debug("Queried food logs", user_id=user_id, date=target_date, results=len(rows))
        return [_serialize_log(log, mapping) for log, mapping in rows]
```

**Loader rewire pattern** — `load_daily_context` becomes:
```python
from datetime import datetime

import structlog
from langgraph.runtime import Runtime

from src.agents.state import AgentState
from src.config import USER_TIMEZONE
from src.context import ContextSchema
from src.services.daily_log_service import query_food_logs

logger = structlog.get_logger(__name__)


async def load_daily_context(state: AgentState, runtime: Runtime[ContextSchema]) -> dict:
    """Fetch today's food log into state via the query_food_logs tool.

    Runs immediately before response_node on every path. See
    docs/adr/0003-daily-log-loader-before-response.md.
    """
    context = runtime.context if runtime.context is not None else ContextSchema()
    user_id = context.user_id
    today_iso = datetime.now(USER_TIMEZONE).date().isoformat()
    logs = await query_food_logs.ainvoke({"target_date": today_iso, "user_id": user_id})
    logger.info("Loaded daily context", user_id=user_id, log_count=len(logs))
    return {"daily_log_today": logs}
```

**Test mock pattern** — replace the dual-mock pattern with a single tool mock:
```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
@patch("src.agents.nodes.load_daily_context_node.query_food_logs")
async def test_returns_logs_from_tool(mock_tool, basic_state):
    mock_tool.ainvoke = AsyncMock(return_value=[SAMPLE_LOG])
    result = await load_daily_context(basic_state, TEST_RUNTIME_A)
    assert result == {"daily_log_today": [SAMPLE_LOG]}
    mock_tool.ainvoke.assert_awaited_once()
    # The call kwargs should include target_date (today, ISO) and user_id
    call_kwargs = mock_tool.ainvoke.call_args.args[0]
    assert call_kwargs["user_id"] == TEST_USER_A
    assert "target_date" in call_kwargs
```

**Integration test pattern for the new range helper** — mirror `TestGetLogsByDateWithMappings` (already in the file from Plan 3d era; if it doesn't exist by that name, find the closest analog).

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation — Service Helper

**Tasks:**
- Add `get_logs_by_date_range_with_mappings` to `src/services/daily_log_service.py`.

### Phase 2: Tool Migration

**Tasks:**
- Migrate `query_food_logs` to use the with-mappings variants on both branches.

### Phase 3: Loader Refactor

**Tasks:**
- Rewire `load_daily_context_node.py` to use the tool.
- Delete the now-dead `get_todays_logs_serialized` service function.

### Phase 4: Tests

**Tasks:**
- Update `tests/unit/test_load_daily_context_node.py` to mock the tool.
- Remove `TestGetTodaysLogsSerialized` from the integration suite.
- Add `TestGetLogsByDateRangeWithMappings` integration tests.
- Run full suites to confirm no regressions.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### 1. UPDATE `src/services/daily_log_service.py` — add `get_logs_by_date_range_with_mappings`

- **IMPLEMENT**: Insert a new helper directly after `get_logs_by_date_range` (line 162-186). Mirror `get_logs_by_date_with_mappings` (lines 132-159) but with the range `where` clause from `get_logs_by_date_range` (lines 180-183). See the *Patterns to Follow* section for the exact body.
- **PATTERN**: Functions live in alphabetical-adjacent placement; group with the other range fn for readability.
- **IMPORTS**: All needed names (`AsyncSession`, `select`, `outerjoin` via select, `func`, `DailyLog`, `CoachFoodMapping`, `uuid_mod`, `DEFAULT_COACH_ID`, `Tuple`, `Optional`, `List`, `date`) are already imported at the top of the file.
- **GOTCHA**: The `outerjoin` on `CoachFoodMapping` must include both the food_id match AND the coach_id match — same as the single-date helper. Forgetting the coach_id clause would join across all coaches.
- **VALIDATE**: `uv run python -c "from src.services.daily_log_service import get_logs_by_date_range_with_mappings; print('OK')"`.

### 2. UPDATE `src/services/daily_log_service.py` — migrate `query_food_logs`

- **IMPLEMENT**: Replace the body of `query_food_logs` (lines 277-288) so both branches use the with-mappings helpers and the comprehension iterates over `(log, mapping)` tuples passing both to `_serialize_log`. See the *Patterns to Follow* section for the exact body. Update the docstring to mention the coach-mapping fields.
- **PATTERN**: `_serialize_log(log, mapping)` already handles the tuple shape (Plan 3d).
- **IMPORTS**: None.
- **GOTCHA**:
  - The single-date branch currently does `logs = await get_logs_by_date(session, user_id, parsed_date)` and `[_serialize_log(log) for log in logs]`. Both halves change.
  - The range branch is the same shape — change both to `rows = ...` and `[_serialize_log(log, mapping) for log, mapping in rows]`.
  - Existing tests asserting `log["protein"]` etc. keep passing — change is additive.
- **VALIDATE**: `uv run pytest tests/integration/test_daily_log_service.py -v -k "query_food_logs"` (existing tests should pass).

### 3. UPDATE `src/agents/nodes/load_daily_context_node.py` — rewire to tool

- **IMPLEMENT**: Replace the file body to match the *Patterns to Follow* — *Loader rewire pattern*. Imports change: drop `get_async_db_session` and `get_todays_logs_serialized`; add `datetime`, `USER_TIMEZONE`, `query_food_logs`. Body computes `today_iso` and calls the tool.
- **PATTERN**: Mirrors how `commit_node` invokes `query_food_logs.ainvoke` (lines 98-100 of `commit_node.py`).
- **IMPORTS**: As described above.
- **GOTCHA**:
  - Keep the `runtime.context is None` defensive guard (mirrors response_node).
  - `today_iso` uses `datetime.now(USER_TIMEZONE).date().isoformat()` — *not* `datetime.now().date()`, which would be UTC on Railway and miss the late-evening Israel logs.
  - The `structlog` logger and the `logger.info("Loaded daily context", ...)` call stay intact.
- **VALIDATE**: `uv run python -c "from src.agents.nodes.load_daily_context_node import load_daily_context; import inspect; assert inspect.iscoroutinefunction(load_daily_context); print('OK')"`.

### 4. UPDATE `src/services/daily_log_service.py` — delete `get_todays_logs_serialized`

- **IMPLEMENT**: Remove the entire `get_todays_logs_serialized` function (lines 228-243).
- **PATTERN**: Function is no longer called anywhere after Task 3.
- **IMPORTS**: If the file imports anything used only by this function, drop those too. Likely `USER_TIMEZONE` is still needed elsewhere (or not — check). The `datetime`, `date`, `Optional`, `Tuple` imports are still needed for other functions.
- **GOTCHA**: Confirm zero remaining callers before deleting:
  - `grep -rn "get_todays_logs_serialized" src bot tests --include='*.py'` should return only the function definition itself (which we're deleting) and possibly the file's docstring at line 7-8 mentioning it.
- **VALIDATE**:
  - `grep -rn "get_todays_logs_serialized" src bot tests --include='*.py'` after deletion — should return either nothing or only the file's own docstring/comments.
  - Update the file's module docstring at line 7-8 if it lists `get_todays_logs_serialized` as one of the public helpers.

### 5. UPDATE `tests/unit/test_load_daily_context_node.py` — mock the tool

- **IMPLEMENT**: Rewrite the three tests to:
  - Mock `query_food_logs.ainvoke` (patch path: `src.agents.nodes.load_daily_context_node.query_food_logs`).
  - Drop the `_fake_session_cm` helper and the `get_async_db_session` patch — no longer needed.
  - Assertions:
    1. Returns logs from the tool.
    2. Empty tool result yields empty list in state.
    3. Calls the tool with `user_id` from runtime context AND `target_date` matching today (Israel local) in ISO format.
- **PATTERN**: See *Test mock pattern* in *Patterns to Follow*.
- **IMPORTS**: Drop `MagicMock` and `asynccontextmanager` if unused after rewrite.
- **GOTCHA**: When asserting `target_date`, freeze time or assert "is a YYYY-MM-DD ISO date string" rather than a hard-coded date string — the test must remain green tomorrow. Easiest: `from datetime import datetime; from src.config import USER_TIMEZONE; expected = datetime.now(USER_TIMEZONE).date().isoformat()` (computed at assertion time, not test definition time).
- **VALIDATE**: `uv run pytest tests/unit/test_load_daily_context_node.py -v` — all 3 tests pass.

### 6. UPDATE `tests/integration/test_daily_log_service.py` — remove `TestGetTodaysLogsSerialized`

- **IMPLEMENT**: Locate the `TestGetTodaysLogsSerialized` class and delete it entirely. Likely 3-4 tests (empty user, today-vs-yesterday scope, user-scoping per the previous plan's notes).
- **PATTERN**: The class is named in the audit/plan history (`TestGetTodaysLogsSerialized` — 3 tests per the 2026-04-17 commit log). Search by class name.
- **IMPORTS**: If no other tests import the helper, drop the import.
- **GOTCHA**: Drop the import of `get_todays_logs_serialized` as well — it's been deleted from the service module.
- **VALIDATE**: `uv run pytest tests/integration/test_daily_log_service.py --collect-only -q` — no `TestGetTodaysLogsSerialized` in the collected list; no import errors.

### 7. UPDATE `tests/integration/test_daily_log_service.py` — add `TestGetLogsByDateRangeWithMappings`

- **IMPLEMENT**: Add a new test class covering:
  1. Returns tuples `(DailyLog, mapping)` for logs with mapped foods (mapping populated).
  2. Returns tuples `(DailyLog, None)` for logs whose food has no mapping for the default coach.
  3. Range `start_date <= timestamp <= end_date` is inclusive on both ends.
  4. User scoping: another user's logs are not returned.
- **PATTERN**: Mirror the existing `TestGetLogsByDateWithMappings` class (single-date variant) — find it in the same file. Use `async_test_db_session`, `TEST_USER_A`, `TEST_USER_B`, `SEED_FOOD_ID` fixtures from `tests/conftest.py`.
- **IMPORTS**: Add `get_logs_by_date_range_with_mappings` to the imports.
- **GOTCHA**: Seed coach mapping is `protein/lean/100g` for `SEED_FOOD_ID` (per `tests/conftest.py:109-117`). Use that to assert the mapping is populated in case 1.
- **VALIDATE**: `uv run pytest tests/integration/test_daily_log_service.py -v -k "TestGetLogsByDateRangeWithMappings"` — all new tests pass.

### 8. UPDATE `tests/integration/test_daily_log_service.py` — extend `query_food_logs` tests for new fields (optional but recommended)

- **IMPLEMENT**: In the existing `query_food_logs` test class, add (or extend) one assertion-style test verifying that the returned dicts carry `category`, `tag`, `serving_amount_g` keys when the food has a coach mapping.
- **PATTERN**: Use the seeded food (`SEED_FOOD_ID` is mapped via `protein/lean/100g`).
- **IMPORTS**: None.
- **GOTCHA**: Pre-existing tests' assertions should not break — change is additive. If any test does `assert log == {<exact dict>}`, that's a strict-equality check that would break; loosen to assert specific keys.
- **VALIDATE**: `uv run pytest tests/integration/test_daily_log_service.py -v -k "query_food_logs"`.

### 9. RUN full unit suite

- **IMPLEMENT**: `uv run pytest tests/unit/`
- **PATTERN**: Pre-commit gate per CLAUDE.md.
- **GOTCHA**: If `commit_node` or `stats_node` unit tests assert exact dict shapes for the `daily_log_report` field they update, those assertions may need additive `category` keys. Update only if a real failure surfaces.
- **VALIDATE**: All unit tests pass.

### 10. RUN integration suite

- **IMPLEMENT**: `uv run pytest tests/integration/`
- **PATTERN**: Real Supabase DB.
- **GOTCHA**: Slow (~6 min over Wi-Fi). Run in background.
- **VALIDATE**: All integration tests pass.

### 11. RUN graph-API suite (cheap insurance — no topology change, but the loader's body changed)

- **IMPLEMENT**: `uv run pytest tests/graph_api/ -v -s`
- **PATTERN**: Mandatory whenever the loader body changes (it now uses a tool with a different mock surface for E2E).
- **VALIDATE**: All graph-API tests pass.

### 12. MANUAL smoke (recommended)

- **IMPLEMENT**: Bot locally with `POLLING_MODE=true` — log a multi-item food list, confirm with "yes", ask "where am I today?" — confirm the response includes a "Today's Totals by Category" block with protein/carb servings (the data is now richer for both today's snapshot and any stats query).
- **VALIDATE**: Visual confirmation in Telegram.

---

## TESTING STRATEGY

### Unit Tests

- `tests/unit/test_load_daily_context_node.py` — rewritten to mock `query_food_logs.ainvoke`. Assertions cover happy path, empty result, correct call args (today ISO + user_id).
- Existing `commit_node`, `stats_node`, `confirmation_node` unit tests — unchanged unless any do strict-equality dict assertions on log shapes (additive change shouldn't break them; flag any that do).

### Integration Tests

- `tests/integration/test_daily_log_service.py`:
  - Remove `TestGetTodaysLogsSerialized` (helper deleted).
  - Add `TestGetLogsByDateRangeWithMappings` (new helper).
  - Optionally extend the `query_food_logs` test class to assert `category` field is present when mapped.

### Graph-API Tests

- Cheap insurance — no topology change but loader internals shifted. Should pass without modification.

### Edge Cases

- **Log with `food_id = NULL`** (CASCADE survivor) — `outerjoin` returns `mapping = None`; `_serialize_log(log, None)` omits the mapping fields. No regression.
- **Food without a coach mapping** — `outerjoin` returns `mapping = None`; same as above. The loader's output is a mix of with- and without-mapping dicts on the same day, depending on per-food data.
- **Empty log day** — `query_food_logs` returns `[]`; loader writes `[]` to state; `_format_daily_log` renders the "Nothing logged yet today." line.
- **Date crossover** — loader computes `today` at request time (per turn). A request that starts at 23:59 Israel and finishes at 00:01 Israel still uses the start-of-request date. Acceptable.
- **Bug 1 (UTC date boundary)** — pre-existing in `func.date(timestamp) == target_date`. Not introduced or worsened by this plan; tracked separately.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
uv run ruff check src/services/daily_log_service.py src/agents/nodes/load_daily_context_node.py tests/unit/test_load_daily_context_node.py tests/integration/test_daily_log_service.py
```

### Level 2: Unit Tests

```bash
uv run pytest tests/unit/
```

### Level 3: Integration Tests

```bash
uv run pytest tests/integration/
```

### Level 4: Graph-API Tests

```bash
uv run pytest tests/graph_api/ -v -s
```

### Level 5: Manual Smoke (Telegram)

Verify the "Today's Totals by Category" block now appears in the system prompt after a CHITCHAT turn (use a thread state inspector or LangSmith trace).

---

## ACCEPTANCE CRITERIA

- [ ] `get_logs_by_date_range_with_mappings` exists in `src/services/daily_log_service.py` and returns `List[Tuple[DailyLog, Optional[CoachFoodMapping]]]`.
- [ ] `query_food_logs` tool body migrated to use the with-mappings variants on both branches; docstring updated.
- [ ] `load_daily_context_node.py` no longer imports `get_async_db_session` or any service function — only the `query_food_logs` tool.
- [ ] `get_todays_logs_serialized` removed from `src/services/daily_log_service.py`.
- [ ] `TestGetTodaysLogsSerialized` removed from integration tests.
- [ ] `TestGetLogsByDateRangeWithMappings` added with at least 4 cases (mapped, unmapped, range inclusivity, user scoping).
- [ ] All unit, integration, and graph-API tests pass.
- [ ] Manual smoke: response system prompt now includes "Today's Totals by Category" block (verified via LangSmith trace or local log).
- [ ] No leftover `get_todays_logs_serialized` references anywhere; no leftover `get_async_db_session` import in the loader.

---

## COMPLETION CHECKLIST

- [ ] All 12 tasks completed in order
- [ ] Each task validation passed immediately
- [ ] `uv run ruff check` clean on all modified files
- [ ] Full unit suite passes
- [ ] Full integration suite passes
- [ ] Full graph-API suite passes
- [ ] Manual smoke confirms category-totals block now renders
- [ ] No regressions in existing functionality
- [ ] Commit message references the previous PR commit (`93c2d2d`) and Plan 3d as the source of the backfill
- [ ] CLAUDE.md unchanged (no architectural drift)

---

## NOTES

### Why no ADR for this change

This is not a decision; it's completing Plan 3d's unfinished migration AND restoring tool-first compliance the previous plan should have required. ADR-0003 already names the loader as following tool-first; this plan delivers on that. The commit log + this plan + the PR description are sufficient.

### Why explicit `target_date` over implicit "today" default

Considered making `query_food_logs` default to today when `target_date` is empty. Rejected because (a) implicit defaults in LLM-callable tools are a small footgun (model could call with no args expecting an error and silently get "today"), and (b) the loader gains exactly one line by being explicit, which is not a real cost. Path A (explicit) chosen over Path C (default).

### Side-effect on `daily_log_report`

`commit_node` and `stats_node` populate `daily_log_report` via `query_food_logs`. After this plan, `daily_log_report` will carry coach-mapping fields too. This is an *upgrade*, not a behavior change for failure paths — every existing reader of `daily_log_report` either ignores the extra keys (LLM context JSON) or already supports them (`QueriedLog` TypedDict has them as Optional). Worth mentioning in the PR description.

### What this does NOT touch

- `commit_node`'s decision logic (only-refresh-if-consumed_at-set) — out of scope; works correctly today.
- The `daily_log_report` field name or shape — preserved.
- `_serialize_log` — already supports the optional mapping arg from Plan 3d.
- Bug 1 (UTC date boundary) — pre-existing; tracked in `brain/TASKS.md`.

### Confidence

**9/10** for one-pass implementation. Low risk because:
- The new helper is a near-mechanical mirror of an existing one.
- The tool migration is purely additive (no consumer breaks).
- The loader rewire is ~10 lines, mirrors `commit_node`'s existing tool call.
- Test surface is well-bounded.

The remaining 10% risk: a strict-equality dict assertion somewhere in the unit suite that breaks on the additive shape change. Easy to fix when surfaced.
