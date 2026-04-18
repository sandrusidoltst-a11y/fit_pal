# RCA: Naive datetime.now() in input_parser_node

## Problem Description

`input_parser_node` injects the current time into its system prompt using `datetime.now()` — a naive, timezone-unaware call. On Railway (UTC host), this produces a time 3 hours behind Israel local time (IDT, UTC+3), misleading the LLM about the time of day when parsing user input.

## Reproduction Steps

1. Deploy to Railway (UTC host) or set `TZ=UTC` locally.
2. Send any message to the bot at, say, 21:00 Israel time.
3. Observe `input_parser_node` receives a system prompt saying `"The current system time is: 18:00:00"` — 3h behind.

## Root Cause Analysis

`src/agents/nodes/input_node.py` line 34:

```python
now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
```

`datetime.now()` without a timezone argument returns the system clock in local wall time. On Railway (UTC), that is UTC. All POC users are in Israel (UTC+3 in summer), so the injected time is always 3h behind.

The identical bug was fixed in `response_node.py` in commit `f3391c4` (2026-04-14), where a `_current_time_str()` helper was introduced using `datetime.now(USER_TIMEZONE)`. The fix was not applied to `input_node.py` at that time.

## Broader Codebase Scan

Searched all `src/` and `bot/` Python files for `datetime.now()` (no tz argument). Only one occurrence found: `src/agents/nodes/input_node.py:34`. No other nodes affected.

## Proposed Fix

Mirror the `response_node` pattern:
1. Extract a `_current_time_str()` helper in `input_node.py` with an optional `now` testability hook.
2. Import `USER_TIMEZONE` from `src.config`.
3. Use `datetime.now(USER_TIMEZONE)` as the default.
4. Add a regression test in `tests/unit/test_input_parser.py` matching `TestCurrentTimeStr` in `test_response_node.py`.

## Validation Commands

```bash
uv run pytest tests/unit/test_input_parser.py -v
uv run pytest tests/unit/ -v
```
