# feat: inject today's daily log into response_node via ContextSchema + Israel-local timestamp serialization

**Date**: 2026-04-17
**Branch**: eval_dolev_conversations
**Commits**: (this session)

**Plan**: `docs/plans/daily-log-injection-and-israel-tz-serialization.md`
**Audit**: `brain/planning/bot-ux-audit-2026-04-17.md` — Fix #2 + Bug 2

## Changes

### Service Layer (Bug 2 — timestamp serialization)
- `_serialize_log` in `src/services/daily_log_service.py` now converts `log.timestamp` from UTC to Israel local time before `.isoformat()`. Single-point fix benefits all downstream consumers: `query_food_logs` tool, `stats_node`'s `daily_log_report`, and the new daily-log injection path.
- Added `get_todays_logs_serialized(session, user_id) -> list[dict]` helper — computes "today in Israel" via `USER_TIMEZONE` and returns serialized dicts. Docstring names the known limitation (Bug 1 near-midnight `func.date()` comparison) with a pointer to the tracked follow-up.

### Runtime Context
- Added `daily_log_today: list[dict]` field to `ContextSchema` (`src/context.py`) with `default_factory=list`. Mirrors the `user_profile` pattern from PR #21.

### Bot Gateway
- Added `_load_todays_log(user_id)` helper — fetches fresh from DB every call (NOT cached on `SessionData`, since the log changes on every commit and stale cache would silently mis-coach).
- Extended `_call_langgraph` signature with `daily_log_today: list[dict] | None = None`. Injected into `body["context"]` with explicit `is not None` check (empty list is a valid, meaningful "nothing logged" signal).
- Wired the per-message fetch into `_handle_authenticated_message` at BOTH call sites: new-input branch AND HITL-resume branch. Missing one would have created a silent bug where resume turns see no log.

### Agent Integration (response_node)
- Added private `_format_daily_log(logs)` helper in `src/agents/nodes/response_node.py`. Always renders a `## Today's Log` markdown section — empty list renders `"Nothing logged yet today."` explicitly, which is the signal the F1 empty-log coach-voice opener (audit Fix #5) will need.
- Wired the section into the `SystemMessage` between `plan_section` and the `Context JSON` block.

### Tests
- **Unit**: added `TestFormatDailyLog` class (2 tests) + 2 new `TestResponseNode` tests asserting the daily log section renders for populated and empty cases. Total unit tests: 122 → **126**.
- **Gateway unit**: updated all 6 `TestMessageRelay` / `TestThreadManagement` / `TestHITLFlow` tests to mock `_load_todays_log` and expect `daily_log_today=[]` in the `_call_langgraph` kwargs.
- **Integration**: added `TestSerializeLogIsraelLocalTimestamp` (1 test — UTC 19:11 → Israel 22:11 with `+03:00` offset) + `TestGetTodaysLogsSerialized` (3 tests — empty user, today-vs-yesterday scope, user-scoping). Total integration tests: 30 → **34**.

## Resolves (bot UX audit findings)
- **F1** — empty-log gaslighting: LLM now sees "nothing logged yet today" explicitly instead of guessing.
- **F3 T1/T2/T3** — no-daily-log-context + brittle-stats-routing: log is always available, no longer depends on `input_parser` → `stats_lookup` routing.
- **F3 T4/T5** — plan-parroting: LLM has both plan + log in the prompt; budget math is now possible (prompt engineering follow-up tracked).
- **F6** — wrong-meal-position: LLM can tell this is the first meal, not the last.
- Partial **F2** display-time — Bug 2 fix at the serializer also lands here for free; the LLM now reads `22:11+03:00` instead of `19:11+00:00`.

## Validation
- `uv run ruff check` on all modified/new files — **passed**
- `uv run pytest tests/unit/ -q` — **126 passed**
- `uv run pytest tests/integration/ -q` — **34 passed**
- Graph-API smoke (manual): not run for this change (no graph-edge / node-routing modifications)

## Next Steps
- **Audit Fix #5 (empty-log coach-voice opener)** is now unblocked — it depends on Fix #1 (timezone, already in Fix #1 changeset) AND this Fix #2 (daily log injection).
- **Audit Fix #6 (budget reasoning template)** is half-unblocked — data now available; Fix #3 (`plan_category`) still needed for correct carb math.
- **POC blocker: Plan vs actual reasoning** — data now available end-to-end.
- **Manual smoke test** — run bot locally with `POLLING_MODE=true`, verify:
  1. Empty-log day: "מה אכלתי היום?" no longer gaslights.
  2. After logging a meal: "what's my status?" references the just-logged item; times render as Israel local.

## Out of scope / follow-ups
- **Bug 1** — `get_logs_by_date` uses `func.date(timestamp) == target_date` which evaluates in the DB session's UTC timezone, so logs made 00:00–03:00 Israel local fall on the previous UTC date and are missed. Tracked in `brain/TASKS.md` Maintenance tier.
- **Token budget** — ~500 tokens/turn added for a full day's log. Acceptable at POC scale.
- **Redis session migration** — `user_profile` still cached per-session (30-min TTL); daily log is explicitly NOT cached to avoid staleness. Full migration is a separate tracked task.
