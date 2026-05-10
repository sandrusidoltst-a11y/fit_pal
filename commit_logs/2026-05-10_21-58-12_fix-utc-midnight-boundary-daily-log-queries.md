# fix(daily-log): UTC midnight boundary in date queries

## Why

`src/services/daily_log_service.py` filtered logs by date with
`func.date(DailyLog.timestamp) == target_date`. Postgres evaluates `date()` over
a `TIMESTAMPTZ` column in the **session timezone** — UTC on Supabase. The
intended user-facing semantic is Asia/Jerusalem-local. Logs written 00:00–02:59
(winter, UTC+2) or 00:00–03:59 (summer DST, UTC+3) Israel-local fell on the
*previous* UTC date and were silently filtered out of "today's logs" queries.

This is the user-reported "missing-serving" symptom from the bot UX audit
(Important #1) — the bot answered as if the user's most recent late-night entry
wasn't there.

## What changed

**One set of helpers, used everywhere.** Five `WHERE` clauses across
`daily_log_service.py` collapsed onto two helpers in `src/config.py`:

- `day_bounds_utc(target_date, tz=USER_TIMEZONE)` — `[start_utc, end_utc)`.
- `timestamp_in_local_day(column, target_date, tz=...)` — single-day predicate.
- `timestamp_in_local_day_range(column, start, end, tz=...)` — inclusive-end
  range, mapped to a half-open UTC window.

Call sites swap from `func.date(DailyLog.timestamp) == target_date` to
`timestamp_in_local_day(DailyLog.timestamp, target_date)` (and the range
analogue for ranges). Function signatures, return shapes, and ORDER BY are
unchanged. Query stays sargable on the existing `timestamp` index (no
`func.date(...)` wrapping).

### Affected predicates (5)

| Function                                     | Before                                       | After                                         |
|----------------------------------------------|----------------------------------------------|------------------------------------------------|
| `get_daily_totals`                           | `func.date(...) == target_date`              | `timestamp_in_local_day(...)`                  |
| `get_logs_by_date`                           | `func.date(...) == target_date`              | `timestamp_in_local_day(...)`                  |
| `get_logs_by_date_with_mappings`             | `func.date(...) == target_date`              | `timestamp_in_local_day(...)`                  |
| `get_logs_by_date_range_with_mappings`       | `func.date(...) >= start AND <= end`         | `timestamp_in_local_day_range(...)`            |
| `get_logs_by_date_range`                     | `func.date(...) >= start AND <= end`         | `timestamp_in_local_day_range(...)`            |

### Why a `tz` parameter with a `USER_TIMEZONE` default

This is the seam for the upcoming per-user timezone work. Today the constant is
hardcoded; when `user_profile.timezone` lands, callers thread the user's tz
through to the helper without changing predicate shape elsewhere.

### Why not `SET TIME ZONE 'Asia/Jerusalem'` on the session

Rejected: couples app correctness to DB session config; breaks if a future
caller opens a session for a different user/timezone; doesn't make the
predicate sargable.

## Tests

- **Unit** (`tests/unit/test_config.py`): 6 new tests — winter UTC+2, summer
  DST UTC+3, 24h half-open shape, predicate compilation (rendered SQL
  contains the right UTC literals + `>=`/`<`), single-day-range equivalence,
  inclusive-end mapping.
- **Integration** (`tests/integration/test_daily_log_service.py`): 4 new
  regression tests, one per affected query function. Each inserts an entry
  with a UTC timestamp on day D-1 that lands on Israel-local day D, queries
  for D, and asserts the row is returned. The totals test is delta-based to
  coexist with `TEST_USER_B`'s pre-existing real Supabase data.

### Validation

| Command                                  | Result                  |
|------------------------------------------|-------------------------|
| `uv run ruff check .`                    | All checks passed       |
| `uv run pytest tests/unit/`              | 185 passed              |
| `uv run pytest tests/integration/`       | 56 passed (148s)        |
| `grep -rn 'func\.date(' src/`            | 0 live uses (comments only) |

## Files

- `src/config.py` — three new helpers next to `serialize_timestamp`.
- `src/services/daily_log_service.py` — 5 predicate swaps.
- `src/models.py` — comment on `DailyLog.timestamp` directing readers to the
  helpers, warning off `func.date()`.
- `tests/unit/test_config.py` — 6 new tests.
- `tests/integration/test_daily_log_service.py` — 4 new regression tests.
- `docs/plans/fix-utc-midnight-boundary-daily-log-queries.md` — plan.
- `commit_logs/2026-05-10_21-58-12_fix-utc-midnight-boundary-daily-log-queries-review-guide.md` — PR reading guide.

## Next steps

- TASKS.md `Important #1` can be marked done when this lands on `main`.
- The same helper signature accepts a `tz` argument; threading it from
  `user_profile.timezone` is the logical follow-up if/when per-user timezone
  is added (currently no story tracking it).
- `personal_stats_service.py` audited via grep — no `func.date(` usage; no
  parallel bug to fix.
