# fix: centralize UTC→Israel-local timestamp serialization; fix naive datetime in input_parser

**Date**: 2026-04-18
**Branch**: `refine_prompts_and_evals`
**Commit**: `1404264`

## Context

Late-session cleanup. Started by noticing `input_parser_node` still used naive `datetime.now()` — same bug that `response_node` had before it was fixed on 2026-04-14. While fixing it, discovered that `personal_stats_service._serialize_stat` was calling raw `.isoformat()` on UTC `recorded_at`, so the LLM received UTC times whenever a user asked about their weight/body fat history. Also noticed that timestamp serialization logic was duplicated across services with no shared reference — a third service could silently ship the bug again.

## Changes

### `src/config.py`
- Added `from datetime import datetime`
- Added `serialize_timestamp(ts: datetime | None) -> str | None` — single utility for converting UTC-stored datetimes to Israel-local ISO strings for LLM consumption. Lives alongside `USER_TIMEZONE` so they stay co-located.

### `src/services/daily_log_service.py`
- Imported `serialize_timestamp` alongside existing `USER_TIMEZONE` import
- `_serialize_log`: replaced 4-line inline `astimezone` block with `serialize_timestamp(log.timestamp)` — no behavior change, just deduplication

### `src/services/personal_stats_service.py`
- Imported `serialize_timestamp` from `src.config`
- `_serialize_stat`: replaced `entry.recorded_at.isoformat() if entry.recorded_at else None` with `serialize_timestamp(entry.recorded_at)` — **bug fix**: was shipping UTC times to the LLM

### `src/agents/nodes/input_node.py`
- Imported `USER_TIMEZONE`
- Extracted `_current_time_str(now=None)` helper with testability hook (mirrors `response_node` pattern)
- Replaced `datetime.now().strftime(...)` with `_current_time_str()` — **bug fix**: was injecting UTC time into the system prompt on Railway

### Tests
- `tests/unit/test_config.py` (new): `TestSerializeTimestamp` — 3 cases: None, UTC→Israel, already-local
- `tests/unit/test_input_parser.py`: added `TestCurrentTimeStr` — asserts 19:11 UTC → 22:11 Israel
- `tests/integration/test_personal_stats_service.py`: added `TestSerializeStatIsraelLocalTimestamp` — real DB regression guard mirroring `TestSerializeLogIsraelLocalTimestamp` in daily_log tests

### Docs
- `docs/rca/naive-datetime-in-input-node.md` — RCA for the input_parser naive datetime bug
- `docs/plans/centralize-timestamp-serialization.md` — implementation plan (executed and complete)

## Validation

- `uv run pytest tests/unit/` — **130 passed**
- `uv run pytest tests/integration/test_personal_stats_service.py tests/integration/test_daily_log_service.py` — **22 passed**

## Next Steps

1. **DB-to-coach-plan sync** — the main feature work. Schema migration (`name_he` + `coach_category` on `food_items`), ingest coach's plan foods, bilingual search in `food_service`, HITL render in Hebrew. Plan: `brain/planning/food-db-coach-plan-sync.md`
2. After DB sync, rerun `eval_input_parser_hebrew.py` — residual failures (cheese slices, protein pudding) should collapse once per-food weights are in the DB.
