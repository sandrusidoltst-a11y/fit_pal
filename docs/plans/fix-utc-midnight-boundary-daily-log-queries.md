# Feature: Fix UTC Midnight Boundary in Daily-Log Date Queries

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files etc.

## Feature Description

`src/services/daily_log_service.py` filters daily logs by date using `func.date(DailyLog.timestamp) == target_date`. Postgres evaluates `date()` over a `TIMESTAMPTZ` column in the **session's timezone**, which on Supabase is UTC. `DailyLog.timestamp` is stored UTC. The intended user-facing semantic for "today" is **Asia/Jerusalem-local** (`USER_TIMEZONE` in `src/config.py`).

Result: a log saved at `02:00 Asia/Jerusalem` on a given Israel-local date is `23:00 UTC` on the *previous* UTC date. A query for "today's logs" with `target_date = today_in_israel` filters this row out — the bot answers as if it isn't there. Audit task #1 in `Important — Real User Quality` (referenced as the "F2 / missing-serving" symptom in `brain/planning/bot-ux-audit-2026-04-17`).

This refactor introduces **one set of helpers** that converts an Israel-local `date` (or date range) into a `[start_utc, end_utc)` half-open window and produces a SQLAlchemy predicate against the timestamp column. All 5 affected query sites in `daily_log_service.py` adopt the helper. The helpers are designed so the only future change for per-user timezone is swapping a default argument.

## User Story

As a user logging meals near or after midnight Israel time
I want the bot to count those entries toward the correct local day when I ask "what did I eat today?"
So that totals, plan-vs-actual reasoning, and the response_node's daily-log context are accurate regardless of the time of day I log

## Problem Statement

Five queries in `src/services/daily_log_service.py` use `func.date(DailyLog.timestamp) {==,>=,<=} <date>`:

| Line | Function | Predicate |
|---|---|---|
| L96 | `get_daily_totals` | `func.date(DailyLog.timestamp) == target_date` |
| L125 | `get_logs_by_date` | `func.date(DailyLog.timestamp) == target_date` |
| L154 | `get_logs_by_date_with_mappings` | `func.date(DailyLog.timestamp) == target_date` |
| L185–186 | `get_logs_by_date_range_with_mappings` | `func.date(...) >= start_date` / `<= end_date` |
| L213–214 | `get_logs_by_date_range` | `func.date(...) >= start_date` / `<= end_date` |

Postgres extracts the date in UTC, but the intended semantic is Asia/Jerusalem-local. Logs in the 00:00–02:59 (winter) / 00:00–03:59 (summer DST) Israel-local window for date D fall on UTC date D-1 and get excluded.

Affected user-facing behavior:
- `stats_node` (`src/agents/nodes/stats_node.py`) — "what did I eat today / on day X" and totals.
- `load_daily_context_node` (`src/agents/nodes/load_daily_context_node.py`) → injects `daily_log_today` into `ContextSchema` for `response_node`. Bot answers using a partial day.
- Tools `query_food_logs` (via `get_logs_by_date_*`) used by graph nodes.

The node callers already compute the *date* correctly (`datetime.now(USER_TIMEZONE).date()`), so the bug is purely on the SQL predicate side.

## Solution Statement

Add timezone-aware helpers in `src/config.py` (next to `serialize_timestamp`):

1. `day_bounds_utc(target_date: date, tz: ZoneInfo = USER_TIMEZONE) -> tuple[datetime, datetime]` — returns `[start_utc, end_utc)` for the given local date.
2. `timestamp_in_local_day(column, target_date: date, tz: ZoneInfo = USER_TIMEZONE) -> ColumnElement[bool]` — SQLAlchemy predicate `column >= start AND column < end`.
3. `timestamp_in_local_day_range(column, start_date: date, end_date: date, tz: ZoneInfo = USER_TIMEZONE) -> ColumnElement[bool]` — same idea, inclusive `start_date` and inclusive `end_date` semantics preserved (end maps to the next day's start in UTC).

Replace all 5 `func.date(...)` predicates in `daily_log_service.py` with calls to the helpers. The helpers default `tz` to `USER_TIMEZONE` so existing call sites stay one-line; future per-user-timezone work threads `tz` from `user_profile` through to the helper without touching the predicate shape.

Add a comment on `DailyLog.timestamp` in `src/models.py` directing future readers to filter via `timestamp_in_local_day` (never `func.date()`).

## Feature Metadata

**Feature Type**: Bug Fix (with a small refactor to centralize the fix)
**Estimated Complexity**: Low
**Primary Systems Affected**:
- `src/config.py` (new helpers)
- `src/services/daily_log_service.py` (5 call sites)
- `src/models.py` (documentation comment on `DailyLog.timestamp`)
- Tests: `tests/unit/test_config.py` (helper unit tests), `tests/integration/test_daily_log_service.py` (regression integration test)

**Dependencies**: None new. Uses stdlib `datetime`, `zoneinfo` (already imported in `src/config.py`), and SQLAlchemy primitives already in use.

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `src/services/daily_log_service.py` (lines 77–219) — Why: contains all 5 buggy predicates and the function signatures that callers depend on. Do not change function signatures or return shapes — only the `WHERE` clause.
- `src/config.py` (lines 1–35) — Why: where `USER_TIMEZONE` is defined and where `serialize_timestamp` lives. The new helpers belong in this file alongside the existing timezone primitive.
- `src/models.py` (lines 36–63) — Why: `DailyLog` model definition; the `timestamp` column at line 53 is the column the helpers operate on. Add a docstring comment here.
- `src/agents/nodes/stats_node.py` (lines 35–45) — Why: a *correct* caller pattern for "today in Israel" — `datetime.now(USER_TIMEZONE).date()`. No changes needed; confirm during validation that this pattern still works.
- `src/agents/nodes/load_daily_context_node.py` (lines 20–35) — Why: the loader that calls `get_logs_by_date_with_mappings` and feeds `ContextSchema.daily_log_today`. No changes needed — verify the helper fixes the symptom here.
- `tests/integration/test_daily_log_service.py` (lines 1–60) — Why: existing test file pattern; the regression test goes here. Note `async_test_db_session` fixture and `TEST_USER_A` / `SEED_FOOD_ID` constants from `tests/conftest.py`.
- `tests/unit/test_config.py` — Why: existing unit-test file for `src/config.py`; helper unit tests go here. Confirm naming and import patterns before adding.
- `tests/conftest.py` — Why: source of `TEST_USER_A`, `SEED_FOOD_ID`, and the `async_test_db_session` fixture used by integration tests. Read once before writing the regression test.

### New Files to Create

None. All changes are additions to existing files.

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [Python `zoneinfo` (stdlib)](https://docs.python.org/3.13/library/zoneinfo.html#zoneinfo.ZoneInfo)
  - Specific section: "Using `ZoneInfo`" + DST handling.
  - Why: confirms `datetime.combine(date, time.min, tzinfo=ZoneInfo(...))` is the right way to anchor "midnight in Asia/Jerusalem"; note that midnight is unambiguous on DST transition days (only the duplicated/skipped *hour* itself is ambiguous, not midnight).
- [SQLAlchemy 2.0 — Operators on Column Elements](https://docs.sqlalchemy.org/en/20/core/operators.html#comparison-operators)
  - Specific section: comparison operators on `Mapped[datetime]` / `TIMESTAMPTZ` columns.
  - Why: confirms direct datetime comparisons (`column >= start`) compile to a sargable predicate that uses the index on `DailyLog.timestamp` (already declared `index=True` in `models.py:53`).
- [Postgres `TIMESTAMPTZ` semantics](https://www.postgresql.org/docs/current/datatype-datetime.html)
  - Specific section: "Time Zones".
  - Why: documents the `func.date(timestamptz)` pitfall — it converts to the session timezone before extracting the date — which is precisely the bug class being fixed.

### Patterns to Follow

**Naming Conventions**

Helpers in `src/config.py` follow snake_case + active-verb naming used by the existing `serialize_timestamp`. Read this signature before naming the new helpers:

```python
# src/config.py:31
def serialize_timestamp(ts: datetime | None) -> str | None: ...
```

The new helpers should sit immediately below `serialize_timestamp`, share the same module-level `USER_TIMEZONE`, and not introduce a new "utils" submodule (one tz primitive lives in config; keep this one there too).

**Type-hinting predicate return**

Use `ColumnElement[bool]` from `sqlalchemy.sql.elements` (or `sqlalchemy.ColumnElement`) for the return type of the predicate helpers. Look at how other modules in this repo type-hint SQLAlchemy expressions before committing — match the project style.

**Service-layer pattern (do not change)**

`daily_log_service.py` keeps the dual-layer pattern: raw service functions (accept `session: AsyncSession`) + `@tool` wrappers below line 221. The helpers are imported into the service file and used **only inside the existing service functions' `.where(...)` clauses**. Do not push them into the tool wrappers — those just delegate.

**Async / DB pattern**

All affected service functions are already `async`. No async changes needed; the helpers are pure functions. Follow `docs/patterns/async-patterns.md` and `docs/patterns/tool-first.md` if anything looks unfamiliar.

**Testing pattern (integration)**

Integration tests for `daily_log_service` live in `tests/integration/test_daily_log_service.py`. They use the `async_test_db_session` fixture and `TEST_USER_A`/`SEED_FOOD_ID` constants from `tests/conftest.py`. AAA structure with one-line docstrings — see lines 22–46 for the canonical example.

**Testing pattern (unit)**

Unit tests for `src/config.py` live in `tests/unit/test_config.py`. The helper tests are pure stdlib (no DB). Follow the existing test naming `test_<unit>_<scenario>`.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation

Add the timezone helpers to `src/config.py` and unit-test them in isolation. This phase has zero behavior change to the live system.

**Tasks:**

- Add `day_bounds_utc`, `timestamp_in_local_day`, and `timestamp_in_local_day_range` to `src/config.py`.
- Add unit tests covering: a regular day, an Israel-local 02:00 boundary case, a DST winter/summer offset difference, and the half-open `[start, end)` shape.

### Phase 2: Core Implementation

Replace the 5 `func.date(...)` predicates in `daily_log_service.py` with the new helpers. Function signatures, return shapes, and ordering all stay the same — only the `WHERE` clause changes.

**Tasks:**

- Update `get_daily_totals` (L96).
- Update `get_logs_by_date` (L125).
- Update `get_logs_by_date_with_mappings` (L154).
- Update `get_logs_by_date_range_with_mappings` (L185–186).
- Update `get_logs_by_date_range` (L213–214).
- Add a comment on `DailyLog.timestamp` in `src/models.py` directing future readers to use the helpers.

### Phase 3: Integration

No router/edge wiring needed. The graph nodes that already pass `datetime.now(USER_TIMEZONE).date()` (`stats_node`, `load_daily_context_node`) automatically get correct results.

**Tasks:**

- Confirm by reading `src/agents/nodes/stats_node.py` and `src/agents/nodes/load_daily_context_node.py` that no caller-side change is needed.
- Spot-grep the rest of `src/` for `func.date(` to confirm there are zero stray usages outside `daily_log_service.py`.

### Phase 4: Testing & Validation

Add a focused integration regression test that mirrors the production failure mode: insert a log with a UTC timestamp on day D-1 that lands on day D in Israel-local, query for date D, assert the row is returned.

**Tasks:**

- Add an integration test in `tests/integration/test_daily_log_service.py` covering `get_logs_by_date` + `get_daily_totals` + `get_logs_by_date_with_mappings` for the boundary case.
- Add a complementary boundary test for the range variants.
- Run the full unit + integration suites.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### CREATE helpers — UPDATE `src/config.py`

- **IMPLEMENT**:
  - Add imports for `date`, `time`, `timedelta`, and `timezone` from `datetime` (some may already be present — check first; the file currently only imports `datetime`).
  - Add `from sqlalchemy import ColumnElement` (or import path matching the project's existing usage) and `from sqlalchemy.sql.elements import ColumnElement` if cleaner — match what the rest of `src/` does.
  - Below `serialize_timestamp`, add three functions:
    ```python
    def day_bounds_utc(target_date: date, tz: ZoneInfo = USER_TIMEZONE) -> tuple[datetime, datetime]:
        """Return [start_utc, end_utc) for the given local date.

        Midnight in `tz` is unambiguous on DST transition days, so this is safe
        to call for any local date without DST hour-folding concerns.
        """
        start_local = datetime.combine(target_date, time.min, tzinfo=tz)
        end_local = start_local + timedelta(days=1)
        return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


    def timestamp_in_local_day(column, target_date: date, tz: ZoneInfo = USER_TIMEZONE):
        """SQLAlchemy predicate: `column` falls within the local-tz day for `target_date`.

        Use this instead of `func.date(column) == target_date` for any TIMESTAMPTZ
        column whose intended day-bucketing is in user-local time. See ADR/audit
        for the UTC-midnight bug class.
        """
        start, end = day_bounds_utc(target_date, tz)
        return (column >= start) & (column < end)


    def timestamp_in_local_day_range(column, start_date: date, end_date: date, tz: ZoneInfo = USER_TIMEZONE):
        """SQLAlchemy predicate: `column` falls within [start_date, end_date] inclusive
        in `tz`. The end bound is converted to the *next* day's UTC start, so
        end_date is inclusive (matching the original `<= end_date` semantics)."""
        start, _ = day_bounds_utc(start_date, tz)
        _, end = day_bounds_utc(end_date, tz)
        return (column >= start) & (column < end)
    ```
- **PATTERN**: `serialize_timestamp` at `src/config.py:31` — same module location, same naming style.
- **IMPORTS**: add only what's missing; do not re-import.
- **GOTCHA**:
  - Do **not** import these helpers in places that don't need them. Helpers belong in `src/config.py` because `USER_TIMEZONE` is already there. If a circular-import issue surfaces during validation (unlikely — `config.py` has no SQLAlchemy session imports), move them to a new `src/utils/time.py` and re-export from `config.py`.
  - The `column` parameter is intentionally untyped at runtime; the return type can be left untyped or annotated as `ColumnElement[bool]`. Match project style.
  - Use `&` (SQLAlchemy bitwise AND) for combining predicates, not Python `and`.
- **VALIDATE**: `uv run python -c "from src.config import day_bounds_utc, timestamp_in_local_day, timestamp_in_local_day_range; from datetime import date; print(day_bounds_utc(date(2026, 5, 10)))"`

### CREATE unit tests — ADD to `tests/unit/test_config.py`

- **IMPLEMENT**: Add tests for the three helpers. Keep them pure-Python (no DB):
  - `test_day_bounds_utc_winter` — for a winter date, assert `start_utc.hour == 22` (Israel UTC+2, midnight local = 22:00 UTC the previous day) and `end_utc - start_utc == 24h`.
  - `test_day_bounds_utc_summer` — for a date inside DST, assert `start_utc.hour == 21` (Israel UTC+3 in DST).
  - `test_day_bounds_utc_half_open_window` — `end - start == timedelta(days=1)` exactly.
  - `test_timestamp_in_local_day_predicate_compiles` — call with a literal column expression (you can use `sqlalchemy.column('ts')`); assert the result compiles to a SQL string that contains `>=` and `<` and the expected UTC literals (use `.compile(compile_kwargs={"literal_binds": True})`).
  - `test_timestamp_in_local_day_range_inclusive_end` — pass `start_date == end_date` and verify the returned window equals the single-day window from `timestamp_in_local_day`.
- **PATTERN**: existing tests in `tests/unit/test_config.py` — match their naming and assertion style.
- **IMPORTS**: `from datetime import date, datetime, timedelta, timezone`; `from src.config import day_bounds_utc, timestamp_in_local_day, timestamp_in_local_day_range, USER_TIMEZONE`.
- **GOTCHA**: pick concrete dates that are unambiguously in winter (e.g. `date(2026, 1, 15)`) and summer DST (e.g. `date(2026, 7, 15)`) for Asia/Jerusalem — Israel DST runs roughly Mar–Oct.
- **VALIDATE**: `uv run pytest tests/unit/test_config.py -v`

### UPDATE `src/services/daily_log_service.py` — `get_daily_totals` (L96)

- **IMPLEMENT**: replace `func.date(DailyLog.timestamp) == target_date` with `timestamp_in_local_day(DailyLog.timestamp, target_date)`.
- **PATTERN**: keep the `.where(DailyLog.user_id == uuid_mod.UUID(user_id), <predicate>)` shape — only swap the predicate.
- **IMPORTS**: at top of file, add `from src.config import timestamp_in_local_day, timestamp_in_local_day_range`.
- **GOTCHA**: do not remove the `func` import — other queries in this file may still use `func.coalesce(...)` and `func.sum(...)`. Verify with a grep before deleting.
- **VALIDATE**: `uv run pytest tests/integration/test_daily_log_service.py::test_get_daily_totals_with_entries -v` (must still pass with the swap; existing fixtures use `datetime.now(timezone.utc)` which is far from the boundary, so they should be unaffected).

### UPDATE `src/services/daily_log_service.py` — `get_logs_by_date` (L125)

- **IMPLEMENT**: replace `func.date(DailyLog.timestamp) == target_date` with `timestamp_in_local_day(DailyLog.timestamp, target_date)`.
- **PATTERN**: same as above; signature, return type, and `.order_by(DailyLog.timestamp)` are unchanged.
- **IMPORTS**: helper already imported in the previous task.
- **GOTCHA**: none.
- **VALIDATE**: `uv run pytest tests/integration/test_daily_log_service.py -v -k get_logs_by_date and not range`

### UPDATE `src/services/daily_log_service.py` — `get_logs_by_date_with_mappings` (L154)

- **IMPLEMENT**: replace `func.date(DailyLog.timestamp) == target_date` with `timestamp_in_local_day(DailyLog.timestamp, target_date)`.
- **PATTERN**: identical swap; the `outerjoin` clause is independent of the date predicate.
- **IMPORTS**: already imported.
- **GOTCHA**: do not move the predicate above the `outerjoin` — keep the `.where()` clause where it is.
- **VALIDATE**: `uv run pytest tests/integration/test_daily_log_service.py -v -k with_mappings`

### UPDATE `src/services/daily_log_service.py` — `get_logs_by_date_range_with_mappings` (L185–186)

- **IMPLEMENT**: replace the two-line `func.date(...) >= start_date` and `<= end_date` predicates with a single call: `timestamp_in_local_day_range(DailyLog.timestamp, start_date, end_date)`.
- **PATTERN**: predicate count goes from 2 to 1; the `user_id` predicate stays.
- **IMPORTS**: already imported.
- **GOTCHA**: the helper preserves inclusive `end_date` semantics — do **not** subtract a day when calling.
- **VALIDATE**: `uv run pytest tests/integration/test_daily_log_service.py -v -k range_with_mappings`

### UPDATE `src/services/daily_log_service.py` — `get_logs_by_date_range` (L213–214)

- **IMPLEMENT**: same two-line → one-line swap with `timestamp_in_local_day_range`.
- **PATTERN**: same as above.
- **IMPORTS**: already imported.
- **GOTCHA**: same as above.
- **VALIDATE**: `uv run pytest tests/integration/test_daily_log_service.py -v -k get_logs_by_date_range and not with_mappings`

### UPDATE `src/services/daily_log_service.py` — clean up unused imports

- **IMPLEMENT**: After all 5 swaps, verify whether `func` from `sqlalchemy` is still needed elsewhere in this file (it is — see `func.coalesce` and `func.sum` in `get_daily_totals`). Leave it. Confirm no dead imports remain.
- **PATTERN**: standard import hygiene.
- **VALIDATE**: `uv run ruff check src/services/daily_log_service.py`

### UPDATE `src/models.py` — annotate `DailyLog.timestamp`

- **IMPLEMENT**: above the `timestamp` column declaration on line 53, add a one-line comment:
  ```python
  # Filter by local-day via `timestamp_in_local_day` from src.config.
  # Never use `func.date(timestamp) == ...` — it evaluates in the DB session timezone (UTC), not user-local.
  ```
- **PATTERN**: short comment that captures the *why* (the bug class), not what.
- **VALIDATE**: `uv run ruff check src/models.py`

### CREATE regression integration test — UPDATE `tests/integration/test_daily_log_service.py`

- **IMPLEMENT**: add a test (or two) that mirrors the production failure mode:
  ```python
  async def test_get_logs_by_date_returns_post_midnight_israel_local(async_test_db_session):
      """A log written at 23:00 UTC on D-1 belongs to Israel-local day D and is returned."""
      from datetime import date, datetime, time, timezone, timedelta
      from src.config import USER_TIMEZONE

      target_local_date = date(2026, 5, 10)
      # 01:30 Asia/Jerusalem on the target date = ~22:30 UTC on the previous day
      local_dt = datetime.combine(target_local_date, time(1, 30), tzinfo=USER_TIMEZONE)
      utc_ts = local_dt.astimezone(timezone.utc)

      await create_log_entry(
          async_test_db_session,
          user_id=TEST_USER_A,
          food_id=SEED_FOOD_ID,
          amount_g=100.0, calories=100.0, protein=10.0, carbs=10.0, fat=2.0,
          timestamp=utc_ts,
          meal_type="snack",
          original_text="late-night snack",
      )

      logs = await get_logs_by_date(async_test_db_session, TEST_USER_A, target_local_date)
      assert len(logs) == 1
      assert logs[0].original_text == "late-night snack"

      totals = await get_daily_totals(async_test_db_session, TEST_USER_A, target_local_date)
      assert totals["calories"] == pytest.approx(100.0)
  ```
  Add a sibling test for the range variants using `target_local_date` as both `start` and `end`.
- **PATTERN**: AAA + one-line docstring; matches existing style at `test_daily_log_service.py:22-46`.
- **IMPORTS**: piggyback on existing imports; add `time` to the `datetime` import line at the top.
- **GOTCHA**:
  - The `async_test_db_session` fixture cleans state between tests (verify in `tests/conftest.py`); do **not** assume an empty DB if it doesn't.
  - Pick a date that is *not* a DST transition date to avoid masking unrelated issues. `2026-05-10` is well inside DST.
- **VALIDATE**: `uv run pytest tests/integration/test_daily_log_service.py -v -k post_midnight_israel_local`

### VALIDATE — full suite

- **IMPLEMENT**: nothing to write.
- **VALIDATE**:
  - `uv run ruff check .`
  - `uv run pytest tests/unit/ -v`
  - `uv run pytest tests/integration/ -v`
- **GOTCHA**: integration tests need `SUPABASE_DB_URL` (or `TEST_DATABASE_URL`) set; if it's not, the fixture skips. Confirm tests actually executed — don't accept a green run that skipped everything.

---

## TESTING STRATEGY

### Unit Tests

`tests/unit/test_config.py`:
- `day_bounds_utc` — winter offset, summer offset, half-open shape.
- `timestamp_in_local_day` — predicate compiles; UTC bounds appear in compiled SQL.
- `timestamp_in_local_day_range` — single-day range matches single-day predicate.

### Integration Tests

`tests/integration/test_daily_log_service.py`:
- Late-night Israel-local entry is returned by `get_logs_by_date` and `get_daily_totals` (the regression test above).
- Same boundary case for `get_logs_by_date_range` and `get_logs_by_date_range_with_mappings` (single-day range form).
- Existing tests must continue to pass — they use mid-day UTC timestamps that aren't near a boundary, so they should be unaffected.

### Edge Cases

- **DST transition day** (Israel spring-forward in late March; fall-back in late October). Midnight is unambiguous on those days; verify the helper still returns a 24h window (or a 23h/25h window around the transition — both behaviors are *correct*; document whichever the code produces). A unit test with a DST transition date guards against future regressions.
- **Same-day range query** — `start_date == end_date`; the helper must return the same window as the single-day form.
- **Date with no entries** — totals query returns zeros (existing test `test_get_daily_totals_empty` covers this).
- **Multiple entries spanning the boundary** — entries at 23:00 UTC and 03:00 UTC on the same Israel-local date should both be returned.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

```bash
uv run ruff check .
```

### Level 2: Unit Tests

```bash
uv run pytest tests/unit/ -v
uv run pytest tests/unit/test_config.py -v
```

### Level 3: Integration Tests

```bash
uv run pytest tests/integration/test_daily_log_service.py -v
uv run pytest tests/integration/ -v
```

### Level 4: Manual Validation

1. Start dev server: `uv run langgraph dev`.
2. In LangSmith Studio (or via the dev bot if configured), insert a `DailyLog` row in Supabase with `timestamp = '<previous UTC date>T22:30:00Z'` (this is roughly 01:30 Israel local on the next day). Use the SQL editor; do **not** mutate via the agent.
3. Send the agent the message "what did I eat today?" with `target_date` resolving to the Israel-local date.
4. Verify the response includes the late-night row and the totals reflect it.
5. Clean up the test row.

(Skip Manual step if no test Supabase rows can be added safely — the integration regression test covers the same pathway.)

---

## ACCEPTANCE CRITERIA

- [ ] Three helpers exist in `src/config.py`: `day_bounds_utc`, `timestamp_in_local_day`, `timestamp_in_local_day_range`.
- [ ] All 5 `func.date(DailyLog.timestamp) ...` predicates in `src/services/daily_log_service.py` are replaced with helper calls. A grep for `func.date(` in `src/` returns zero hits.
- [ ] `DailyLog.timestamp` in `src/models.py` carries a comment directing readers to the helpers.
- [ ] `tests/unit/test_config.py` has unit tests covering winter/summer offsets, half-open shape, and predicate compilation.
- [ ] `tests/integration/test_daily_log_service.py` has at least one regression test asserting that a 22:30 UTC entry on D-1 is returned for Israel-local date D via `get_logs_by_date` + `get_daily_totals`.
- [ ] `uv run ruff check .` passes.
- [ ] `uv run pytest tests/unit/ tests/integration/` passes.
- [ ] No existing test was modified except to add new cases.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit + integration)
- [ ] No linting or type checking errors
- [ ] Manual testing confirms feature works (or the integration regression test stands in)
- [ ] Acceptance criteria all met
- [ ] Code reviewed for quality and maintainability

---

## NOTES

**Why `[start, end)` half-open windows.** Standard ranged-time idiom; avoids double-counting the instant at midnight. End-date inclusivity is preserved by mapping `end_date`'s day to *next-day midnight* in UTC.

**Why a `tz` parameter with a `USER_TIMEZONE` default.** This is the future-proofing seam for per-user timezone (the only "user story that stresses the design" surfaced during discussion). When `user_profile.timezone` lands, callers can thread the trainee's tz through to the helper without changing the call shape elsewhere.

**Why no separate `src/utils/time.py` module.** `USER_TIMEZONE` and `serialize_timestamp` already live in `src/config.py`; co-locating the new helpers preserves "one place for tz primitives". Promote to `src/utils/time.py` if/when this set grows beyond ~5 functions.

**Out of scope.**
- Per-user timezone storage on `user_profile`. Tracked separately; this PR only positions the helpers to accept it.
- `personal_stats_log` audit. Verified by grep that it does *not* use `func.date(`, so no parallel bug exists there. (`src/services/personal_stats_service.py`.)
- Session-level `SET TIME ZONE 'Asia/Jerusalem'` workaround. Rejected because it (a) couples app correctness to DB session config, (b) breaks if a future caller opens a session for a different user/timezone, and (c) doesn't make the predicate sargable.

**Confidence Score: 9/10** — fix is small, mechanical, and well-bounded. The one risk is an unforeseen import ordering quirk in `src/config.py` (e.g. SQLAlchemy import inflating cold-start); fallback is moving helpers to `src/utils/time.py` and re-exporting.
