# Feature: Centralize UTC→Israel-Local Timestamp Serialization

The following plan should be complete, but validate codebase patterns before implementing.

Pay special attention to import paths — `USER_TIMEZONE` lives in `src/config.py` and that's where the new utility goes too.

## Feature Description

A `serialize_timestamp(ts)` utility lives in `src/config.py` alongside `USER_TIMEZONE`. Both services that emit timestamps to the LLM (`daily_log_service`, `personal_stats_service`) import and call it instead of duplicating (or missing) the conversion inline.

This also fixes a live bug: `personal_stats_service._serialize_stat` currently calls `.isoformat()` on the raw UTC `recorded_at` value — the LLM sees UTC times instead of Israel local time when a user asks about their weight/body fat history.

## User Story

As the FitPal system,
I want timestamp serialization to live in one place,
So that adding a new service never silently ships UTC times to the LLM.

## Problem Statement

- `daily_log_service._serialize_log` does the conversion correctly: `log.timestamp.astimezone(USER_TIMEZONE).isoformat()`
- `personal_stats_service._serialize_stat` skips it: `entry.recorded_at.isoformat()` → raw UTC
- If a third service is added, there's no shared reference — the bug can recur

## Solution Statement

Extract one pure helper into `src/config.py`:

```python
def serialize_timestamp(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    return ts.astimezone(USER_TIMEZONE).isoformat()
```

Replace both inline implementations with a call to it.

## Feature Metadata

**Feature Type**: Refactor + Bug Fix  
**Estimated Complexity**: Low  
**Primary Systems Affected**: `src/config.py`, `src/services/daily_log_service.py`, `src/services/personal_stats_service.py`  
**Dependencies**: None new — `USER_TIMEZONE` already in `src/config.py`

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ BEFORE IMPLEMENTING

- `src/config.py` (full file) — Where `USER_TIMEZONE` is defined; new utility goes here
- `src/services/daily_log_service.py` (lines 163–186) — `_serialize_log` has the correct inline pattern to replace
- `src/services/personal_stats_service.py` (lines 112–119) — `_serialize_stat` has the broken inline pattern to fix
- `tests/integration/test_daily_log_service.py` (lines 314+) — Regression guard for timezone serialization; follow same pattern for personal stats test
- `tests/unit/test_response_node.py` (lines 158–173) — `TestCurrentTimeStr` pattern: fixed UTC instant → assert Israel-local string

### New Files to Create

None — only modifications to existing files.

### Patterns to Follow

**Utility placement**: Config-level utilities that depend on `USER_TIMEZONE` live in `src/config.py`. Example: `USER_TIMEZONE = ZoneInfo("Asia/Jerusalem")` is already there.

**Correct serialization pattern** (from `daily_log_service.py:170–172`):
```python
ts_local = (
    log.timestamp.astimezone(USER_TIMEZONE).isoformat()
    if log.timestamp
    else None
)
```

**Timezone regression test pattern** (from `test_response_node.py:168–172`):
```python
def test_utc_instant_renders_in_israel_local_time(self):
    utc_moment = datetime(2026, 4, 16, 19, 11, tzinfo=timezone.utc)
    result = _current_time_str(now=utc_moment)
    assert "22:11" in result
```

**Import pattern in services**:
```python
from src.config import USER_TIMEZONE  # existing in daily_log_service
# becomes:
from src.config import serialize_timestamp
```

---

## IMPLEMENTATION PLAN

### Phase 1: Add utility to config.py

Add `serialize_timestamp` to `src/config.py` right after the `USER_TIMEZONE` definition.

### Phase 2: Update services

Replace inline patterns in both services with `serialize_timestamp(...)` calls.

### Phase 3: Tests

Add a unit test for `serialize_timestamp` directly. Add a regression test asserting personal stats serialization emits Israel-local time.

---

## STEP-BY-STEP TASKS

### UPDATE `src/config.py`

- **ADD** `from datetime import datetime` to imports (check if already present — it may not be)
- **ADD** after `USER_TIMEZONE = ZoneInfo("Asia/Jerusalem")`:
```python
def serialize_timestamp(ts: datetime | None) -> str | None:
    """Serialize a UTC-stored datetime to Israel-local ISO string for LLM consumption."""
    if ts is None:
        return None
    return ts.astimezone(USER_TIMEZONE).isoformat()
```
- **GOTCHA**: `config.py` currently imports `datetime` only implicitly via other imports — add it explicitly
- **VALIDATE**: `uv run python -c "from src.config import serialize_timestamp; print(serialize_timestamp(None))"`

### UPDATE `src/services/daily_log_service.py`

- **REFACTOR** import: replace `from src.config import USER_TIMEZONE` with `from src.config import serialize_timestamp`
- **REFACTOR** `_serialize_log` (lines 163–186): replace the inline 4-line `ts_local` block:
  ```python
  # REMOVE:
  ts_local = (
      log.timestamp.astimezone(USER_TIMEZONE).isoformat()
      if log.timestamp
      else None
  )
  # REPLACE WITH:
  ts_local = serialize_timestamp(log.timestamp)
  ```
- **GOTCHA**: `USER_TIMEZONE` is only used in `_serialize_log` and `get_todays_logs_serialized` — after the refactor, `get_todays_logs_serialized` still uses `datetime.now(USER_TIMEZONE).date()` directly, so keep that import or import `USER_TIMEZONE` alongside `serialize_timestamp`
- **VALIDATE**: `uv run pytest tests/integration/test_daily_log_service.py -v`

### UPDATE `src/services/personal_stats_service.py`

- **ADD** import: `from src.config import serialize_timestamp`
- **FIX** `_serialize_stat` (line 118): replace
  ```python
  # REMOVE:
  "recorded_at": entry.recorded_at.isoformat() if entry.recorded_at else None,
  # REPLACE WITH:
  "recorded_at": serialize_timestamp(entry.recorded_at),
  ```
- **VALIDATE**: `uv run pytest tests/integration/test_personal_stats_service.py -v`

### ADD unit tests

**File**: `tests/unit/test_config.py` (create if it doesn't exist)

- **ADD** `TestSerializeTimestamp` class:
  - `test_none_returns_none` — `serialize_timestamp(None)` returns `None`
  - `test_utc_converts_to_israel_local` — `datetime(2026, 4, 16, 19, 11, tzinfo=timezone.utc)` → assert `"22:11"` and `"+03:00"` in result
  - `test_already_local_passthrough` — aware datetime in `USER_TIMEZONE` serializes correctly
- **PATTERN**: mirror `TestCurrentTimeStr` in `tests/unit/test_response_node.py:161–173`
- **VALIDATE**: `uv run pytest tests/unit/test_config.py -v`

---

## TESTING STRATEGY

### Unit Tests

`tests/unit/test_config.py` — pure function, no DB needed. Three cases: None input, UTC input, already-local input.

### Integration Tests

Existing integration tests for both services cover the serialized output format. Run both suites to confirm no regressions.

### Edge Cases

- `None` timestamp → must return `None` not crash
- Already timezone-aware datetime in a non-UTC zone → `astimezone` handles this correctly (no double-conversion)
- Naive datetime (no tz info) → `astimezone` on a naive datetime raises `ValueError` on Python 3.x — this is acceptable; all DB timestamps are stored with tz info (Supabase `timestamptz`)

---

## VALIDATION COMMANDS

```bash
# Level 1: import sanity
uv run python -c "from src.config import serialize_timestamp; print('ok')"

# Level 2: unit tests
uv run pytest tests/unit/test_config.py -v
uv run pytest tests/unit/ -v

# Level 3: integration tests
uv run pytest tests/integration/test_daily_log_service.py -v
uv run pytest tests/integration/test_personal_stats_service.py -v
```

---

## ACCEPTANCE CRITERIA

- [ ] `serialize_timestamp` in `src/config.py`, importable and documented
- [ ] `daily_log_service._serialize_log` uses `serialize_timestamp` — no inline `astimezone` call
- [ ] `personal_stats_service._serialize_stat` uses `serialize_timestamp` — UTC bug fixed
- [ ] Unit tests for `serialize_timestamp`: None, UTC→Israel, aware→aware
- [ ] All existing integration tests pass — zero regressions
- [ ] Full unit suite passes (127+ tests)

---

## NOTES

- `get_todays_logs_serialized` in `daily_log_service` still calls `datetime.now(USER_TIMEZONE).date()` directly — that's correct and should not be changed (it's generating "now", not serializing a stored timestamp)
- `_current_time_str()` in `response_node` and `input_node` are a different concern (current time for LLM prompts) — do not touch them
- No migration needed — this is a pure display-layer change; stored data in Supabase remains UTC `timestamptz`
