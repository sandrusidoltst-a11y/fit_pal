# PR Reading Guide — UTC Midnight Boundary in Daily-Log Queries

Read in this order. Each step builds on the previous one.

## 1. Why we're here

- **Plan**: [`docs/plans/fix-utc-midnight-boundary-daily-log-queries.md`](./fix-utc-midnight-boundary-daily-log-queries.md) — bug class, decision matrix, design seam for per-user timezone.
- **Commit log**: `commit_logs/2026-05-10_21-58-12_fix-utc-midnight-boundary-daily-log-queries.md` — what shipped and why this shape.
- **Audit source**: `Important — Real User Quality #1` in `brain/TASKS.md` (the "missing-serving" symptom; user logs at 01:30 Israel local, bot answers as if entry isn't there).

## 2. The keystone change — `src/config.py`

Read this **first** before any service code. Three new helpers below
`serialize_timestamp`:

- `day_bounds_utc(target_date, tz=USER_TIMEZONE)` — half-open UTC window for a
  local date.
- `timestamp_in_local_day(column, target_date, tz=...)` — `>=` AND `<`
  predicate; replaces `func.date(column) == target_date`.
- `timestamp_in_local_day_range(column, start_date, end_date, tz=...)` —
  inclusive-end range, mapped to next-day-start in UTC.

The `tz` parameter defaults to `USER_TIMEZONE` so existing call sites stay
one-line; this is also the seam for future per-user timezone.

## 3. The readers — `src/services/daily_log_service.py`

Five `.where(...)` clauses, one mechanical swap each. Read in file order:

1. `get_daily_totals` (`func.date(...) == target_date` → `timestamp_in_local_day`).
2. `get_logs_by_date` — same swap.
3. `get_logs_by_date_with_mappings` — same swap.
4. `get_logs_by_date_range_with_mappings` — two-line predicate
   (`func.date >= start` + `<= end`) collapses to one call:
   `timestamp_in_local_day_range(...)`.
5. `get_logs_by_date_range` — same range collapse.

Function signatures, return shapes, and `ORDER BY` are unchanged. The `func`
import stays — it's still used by `func.coalesce`/`func.sum` in
`get_daily_totals`.

## 4. Adjacent — `src/models.py`

A two-line comment above the `DailyLog.timestamp` column declaration directs
future readers to the helper and warns off `func.date()`. This is the only
change to the model.

## 5. Tests — by tier

Read tests in this order; each tier independently confirms a different
property of the fix.

1. **`tests/unit/test_config.py`** — pure-stdlib tests for the helpers. Don't
   touch the DB. Cover: winter UTC+2, summer DST UTC+3, 24h half-open shape,
   predicate compilation against literal UTC bounds, single-day range
   equivalence, inclusive-end mapping.
2. **`tests/integration/test_daily_log_service.py`** — four regression tests
   appended after `test_log_filtering_per_user`. Each inserts an entry whose
   UTC date is *the day before* the Israel-local date being queried, and
   asserts that the entry comes back. One per affected query function.

The totals regression test asserts a **delta** rather than an absolute total —
`TEST_USER_B` carries real production-shape data on `2026-05-10` (4390 cal),
so an absolute assertion fails non-deterministically. Delta is what we
actually want to test: "the boundary entry is counted."

## Things worth flagging while reviewing

1. **`tz` defaults to `USER_TIMEZONE`** in all three helpers. This is
   deliberately positioned as a seam for future per-user timezone — no story
   currently tracks it, but the signature is set up to accept it cleanly. If
   you'd rather force callers to pass `tz` explicitly, that's an easy follow-up.
2. **`func` import stays** in `daily_log_service.py`. Verified by grep —
   `func.coalesce` and `func.sum` are still in use inside `get_daily_totals`.
   The lint rule "ban `func.date(`" is enforceable in CI if we want it; not
   added here.
3. **No new tz utility module.** Helpers go in `src/config.py` next to
   `serialize_timestamp` because that's where `USER_TIMEZONE` already lives.
   Promote to `src/utils/time.py` only if this set grows beyond ~5 functions.
4. **DST safety.** Midnight in Asia/Jerusalem is unambiguous on transition
   days (the duplicated/skipped *hour* is not midnight), so
   `datetime.combine(date, time.min, tzinfo=ZoneInfo)` is safe. Spring-forward
   day produces a 23h window; fall-back produces a 25h window. Both are
   *correct* — they reflect the actual local day boundaries.
5. **Inclusive-end semantics preserved.** The original
   `func.date(...) <= end_date` was inclusive of `end_date`. The range helper
   maps `end_date` to *next-day midnight* in UTC, preserving inclusivity. A
   single-day range (`start_date == end_date`) compiles to the same SQL as
   `timestamp_in_local_day` — there's a unit test asserting this.
6. **`personal_stats_log` audited via grep** — no `func.date(` usage there.
   No parallel bug to fix.

## Skip-able

- The `import` line additions in `src/config.py`, `src/services/daily_log_service.py`,
  and the test files are mechanical — they bring in `time`, `timedelta`,
  `timezone`, and the new helpers.
- The plan and this guide are documentation; if you've read the commit log,
  they don't add new technical content.
