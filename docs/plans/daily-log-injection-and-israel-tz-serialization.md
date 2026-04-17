# Feature: Daily Log Injection via ContextSchema + Israel-local Timestamp Serialization

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files.

## Feature Description

Inject each user's **current-day food log** into `response_node`'s `SystemMessage` on every turn, via `ContextSchema` — the same pattern PR #21 used for `user_profile` and `nutrition_plan`. The agent will always know what the user has eaten today without depending on the input-parser routing to `stats_lookup`.

Also fix a **silent display bug** that already exists across the whole app: `DailyLog.timestamp` is stored in UTC, and `_serialize_log` in `daily_log_service.py` emits the raw UTC ISO string downstream. The LLM ends up seeing (and sometimes parroting) "22:00" when the user ate at "01:30 Israel." Fold this fix into the same change by converting UTC → Israel local time at the single-point serializer; this automatically benefits `stats_node`'s `daily_log_report` and the `query_food_logs` public tool as well.

Both changes are derived from the bot UX audit on 2026-04-17 — see `brain/planning/bot-ux-audit-2026-04-17.md`, Workstream 1 item #2 (daily log injection) and the Bug 2 discussion that emerged during the Fix #2 planning session.

## User Story

As a **trainee**,
I want the bot to already know what I've eaten today when I ask "what's my status?" or "should I eat this?",
So that it doesn't have to guess, doesn't have to be corrected, and doesn't gaslight me with "I don't have access to today's log."

As a **trainee in Israel**,
I want the bot's timestamps and "today" to match my local day,
So that reported meal times are actually the times I ate, not UTC values three hours behind.

As **Dolev (the developer)**,
I want the per-user daily log to flow through the same context-injection pattern as `user_profile` and `nutrition_plan`,
So that the architecture stays coherent and future "per-user X" fields follow a single well-understood pattern.

## Problem Statement

Three real failures from the audit:

1. **Empty-log gaslighting (F1)** — bot responds to "what's my status?" with "No daily data is available… try checking the entered data or try typing again if something didn't register." Plants doubt that the user logged something that got lost. Tone is system-message-y, zero coaching.
2. **Brittle stats routing (F3 T1/T2/T3)** — same natural question, different phrasing, opposite route: sometimes the input parser lands on `QUERY_DAILY_STATS` and `stats_lookup` runs, sometimes it doesn't and the LLM says "I don't see meal logs from today." One turn of explicit challenge from the user ("are you sure you can't check today's log?") unblocks it. Unusable.
3. **Plan-parroting instead of coaching (F3 T4/T5, F6)** — even when the log is fetched, bot doesn't reason over *remaining budget given time-of-day*. And without the log, it can't tell if a given meal is the first of the day or the last — F6 thread shows it calling a noon meal "finishing the day."

Two underlying causes:
- **`response_node` has no ambient daily-log context.** It must rely on `stats_node` (hit-or-miss routing) or guess.
- **Timestamps are stored and emitted in UTC.** On a UTC-hosted LangGraph server (Railway), everything downstream — including the LLM's reasoning and any user-facing time references — is 3 hours behind Israel. This is the Bug 2 we named during planning.

## Solution Statement

**Architecture (mirror PR #21 nutrition-plan injection):**

1. Add `daily_log_today: list[dict]` field to `ContextSchema` (default `[]`).
2. In `bot/gateway.py`, fetch today's log **every message** (profile stays cached per-session, log does not — it changes on every commit) and attach it to the outgoing `context` body.
3. In `response_node`, read `runtime.context.daily_log_today`, format it inline via a small private helper, and prepend it to the `SystemMessage` — same shape as the existing `## User Nutrition Plan` section.

**Serializer fix (Bug 2):**

4. Modify `_serialize_log` in `src/services/daily_log_service.py` to `.astimezone(USER_TIMEZONE)` before `.isoformat()`. Single-point change; affects `daily_log_today` (new path), `query_food_logs` tool, and `stats_node`'s `daily_log_report` (existing consumers).

**Scope carve-out:**

5. Bug 1 (near-midnight `func.date(ts) == target_date` comparison runs in UTC, so logs made 00:00–03:00 Israel local fall on previous UTC date and get missed) is **out of scope** — add a follow-up task to `brain/TASKS.md` Maintenance tier.

## Feature Metadata

**Feature Type**: Enhancement + Bug Fix
**Estimated Complexity**: Medium
**Primary Systems Affected**:
- `src/context.py` (schema extension)
- `src/services/daily_log_service.py` (Bug 2 + new helper)
- `bot/gateway.py` (per-message fetch + context body wiring)
- `src/agents/nodes/response_node.py` (render injection)
- Tests: `tests/unit/test_response_node.py`, `tests/integration/test_daily_log_service.py` (new), `tests/unit/test_gateway.py`

**Dependencies**: None new. `USER_TIMEZONE` constant already exists in `src/config.py` from Fix #1 (this session). `zoneinfo` is stdlib.

**Resolves (bot UX audit findings)**:
- **F1** — empty-log gaslighting / plan-unaware (now LLM sees "today: nothing logged yet" explicitly and can open the day coachingly)
- **F3 T1/T2/T3** — no-daily-log-context + brittle-stats-routing (removed by ambient context)
- **F3 T4/T5** — plan-parroting-not-coaching (LLM now has log + plan both available in prompt; budget math becomes possible)
- **F6** — wrong-meal-position (LLM can tell "this is the first meal today")
- Partial unblock of **F2** display-time references via Bug 2 fix (LLM will see 22:00 local instead of 19:00 UTC)

**TASKS.md impact**:
- Closes `Fix daily context loss in bot` (Important tier)
- Unblocks the POC blocker `Plan vs actual reasoning — agent compares daily intake to targets` (Critical tier) — the context carries what's eaten; a follow-up prompt-engineering fix (Fix #6 from the audit) will make the LLM reason over remaining budget.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

- `src/context.py` (entire file, 51 lines) — `ContextSchema` dataclass + `UserProfile` TypedDict + `DEFAULT_DEV_PROFILE`. Mirror the `user_profile: dict = field(default_factory=...)` pattern for the new `daily_log_today` field.
- `docs/patterns/runtime-context.md` — canonical architecture doc for the runtime-context pattern. Defines how bot → context body → ContextSchema → Runtime → node flow works.
- `docs/plans/per-user-nutrition-plan-injection.md` — the completed plan for PR #21. This is the blueprint. Task structure and phase ordering mirror it.
- `commit_logs/2026-04-13_20-15-00_feat-nutrition-plan-injection.md` — how PR #21 actually shipped, including test counts and loose ends.
- `commit_logs/2026-04-02_23-55-00_migrate-runtime-context-schema.md` — original migration to `ContextSchema` / `Runtime`. Establishes why nodes take `runtime: Runtime[ContextSchema]` as the second parameter and why tools accept plain string `user_id`.
- `brain/learnings/pr21-nutrition-plan-review.md` — post-merge lessons on PR #21. Notes the 30-min session cache limitation on plan-refresh (same limitation applies here for profile, not for log since log is fetched fresh every message).
- `brain/planning/bot-ux-audit-2026-04-17.md` — the audit findings and Workstream 1 item #2 (this fix).
- `src/agents/nodes/response_node.py` (lines 81-132, and especially lines 94-122) — current `response_node`. The `profile_section` pattern (line 98-104) is what we mirror for the daily log section. Also lines 2-3, 14-16, and the new `_current_time_str` helper added this session at line 26 — pattern for "private helper in this module."
- `src/services/daily_log_service.py` (entire file, 221 lines) — `get_logs_by_date` (lines 108-128), `_serialize_log` (lines 162-175), and `query_food_logs` tool (lines 209-220). We modify `_serialize_log` for Bug 2 and add `get_todays_logs_serialized` helper.
- `src/agents/nodes/stats_node.py` (entire file, 37 lines) — existing consumer of `query_food_logs.ainvoke` that writes to `state["daily_log_report"]`. Confirms the tool returns `list[dict]`; also shows the existing "today = date of consumed_at or today UTC" pattern which is the exact bug we're fixing at the serializer layer.
- `bot/gateway.py` (lines 64-65, 90-117, 189-313) — `SessionData` TypedDict (daily log is NOT added here — it's fetched fresh each call, not cached on session). `_call_langgraph` signature + body construction (lines 90-117); `_handle_authenticated_message` per-message flow (lines 268-343); `_load_user_profile` (lines 204-207) is the fetch-once-cache pattern we explicitly **do not** repeat for daily log.
- `src/agents/state.py` (lines 33-48) — `QueriedLog` TypedDict. Same shape we'll put into `daily_log_today` via `_serialize_log` (serialized dict form).
- `src/config.py` (lines 16-22) — `USER_TIMEZONE = ZoneInfo("Asia/Jerusalem")` added in Fix #1 this session. Import from here; do NOT redefine.
- `tests/unit/test_response_node.py` (entire file, 340 lines) — test pattern. Uses `_make_state()` helper, `TEST_RUNTIME_A` from `tests.conftest`, and `@patch("src.agents.nodes.response_node.get_llm_for_node")` to capture the `SystemMessage` content. Also `TestCurrentTimeStr` (added this session in Fix #1, lines 152-170) — pattern for a private-helper test in this file.
- `tests/integration/test_user_profile_service.py` (entire file, 118 lines) — integration test pattern: `async_test_db_session` fixture, `TEST_USER_A`, direct service function calls. Mirror this structure for the new `tests/integration/test_daily_log_service.py`.
- `tests/conftest.py` (entire file, 173 lines) — `TEST_RUNTIME_A`, `TEST_USER_A`, `async_test_db_session` fixture, `SEED_FOOD_ID`. `basic_state` fixture already includes `daily_log_report: []` — do NOT add `daily_log_today` to state; it's context-only, not state.
- `tests/unit/test_gateway.py` — existing gateway unit tests. Examine the onboarding / profile-load mock patterns to decide whether a `_load_todays_log` test belongs here or in a new integration test. (Check current structure during implementation.)
- `src/agents/nutritionist.py` — graph registration. `context_schema=ContextSchema` already wired; nothing changes here, but confirm during validation.

### New Files to Create

- `tests/integration/test_daily_log_service.py` — integration tests for the new `get_todays_logs_serialized` helper and the updated `_serialize_log` UTC→Israel conversion.

### Relevant Documentation — YOU SHOULD READ THESE BEFORE IMPLEMENTING

- [LangGraph Runtime Context](https://langchain-ai.github.io/langgraph/concepts/low_level/#context) — `context_schema` on `StateGraph`, typed runtime context, and the `Runtime[ContextSchema]` parameter.
  - Why: confirms the official API for extending context schemas. We're adding a field, not changing how context flows.
- [Python `zoneinfo` stdlib](https://docs.python.org/3/library/zoneinfo.html) — `ZoneInfo` class, `datetime.astimezone(tz)`.
  - Why: Bug 2 fix uses `datetime.astimezone(USER_TIMEZONE).isoformat()`.
- [SQLAlchemy `DateTime(timezone=True)` with asyncpg](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#postgresql-data-types) — clarifies that asyncpg returns aware UTC datetimes; `astimezone()` re-expresses without altering the absolute instant.
  - Why: confirms `log.timestamp` is already aware; we just convert the representation.

### Patterns to Follow

**ContextSchema field addition (mirror `user_profile`):**

```python
# src/context.py — pattern to mirror, do NOT literally copy
@dataclass
class ContextSchema:
    user_id: str = DEFAULT_DEV_USER_ID
    user_profile: dict = field(default_factory=lambda: DEFAULT_DEV_PROFILE.copy())
    daily_log_today: list[dict] = field(default_factory=list)  # NEW

    def __post_init__(self):
        try:
            uuid.UUID(self.user_id)
        except (ValueError, AttributeError):
            self.user_id = DEFAULT_DEV_USER_ID
```

Use `field(default_factory=list)` — NOT `= []` (mutable default trap).

**Serializer UTC → Israel conversion (Bug 2 fix):**

```python
# src/services/daily_log_service.py — _serialize_log
def _serialize_log(log: DailyLog) -> dict:
    """Convert a DailyLog ORM object to a JSON-serializable dict.

    Timestamps are stored UTC in Postgres; we emit them in Israel local time
    so downstream consumers (LLM, response_node, stats_node) read the time
    the user actually experienced. See bot UX audit F2/Bug 2.
    """
    ts_local = (
        log.timestamp.astimezone(USER_TIMEZONE).isoformat()
        if log.timestamp
        else None
    )
    return {
        "id": str(log.id),
        "food_id": str(log.food_id) if log.food_id else None,
        "amount_g": log.amount_g,
        "calories": log.calories,
        "protein": log.protein,
        "carbs": log.carbs,
        "fat": log.fat,
        "timestamp": ts_local,
        "meal_type": log.meal_type,
        "original_text": log.original_text,
    }
```

Import `USER_TIMEZONE` from `src.config` at the top of the file.

**Thin "today" helper in the service layer (Option C from planning discussion):**

```python
# src/services/daily_log_service.py — new function, placed after get_logs_by_date_range
async def get_todays_logs_serialized(
    session: AsyncSession, user_id: str
) -> list[dict]:
    """Return today's logs for a user (in Israel local day), serialized for context injection.

    Encapsulates the 'today in Israel' date computation + serialization in one place
    so the bot gateway doesn't need to touch ORM objects or the private serializer.

    KNOWN LIMITATION: `get_logs_by_date` uses `func.date(timestamp) == target_date`
    which evaluates in the DB session's timezone (UTC on Supabase). Logs made
    00:00-03:00 Israel local time fall on the previous UTC date and are missed.
    Follow-up task tracked in brain/TASKS.md. See Bug 1 in the fix plan.
    """
    today = datetime.now(USER_TIMEZONE).date()
    logs = await get_logs_by_date(session, user_id, today)
    return [_serialize_log(log) for log in logs]
```

**Bot per-message fetch (NOT cached — profile caching pattern does NOT apply):**

```python
# bot/gateway.py — new helper, placed next to _load_user_profile
async def _load_todays_log(user_id: str) -> list[dict]:
    """Fetch today's food log for the user, fresh every call.

    Unlike user_profile, this is NOT cached on the session — the log changes
    on every food commit and stale cache would silently mis-coach the user.
    """
    async with get_async_db_session() as session:
        return await get_todays_logs_serialized(session, user_id)
```

Called in `_handle_authenticated_message` after the profile is ensured-loaded, BEFORE the `_call_langgraph` invocation.

**`_call_langgraph` signature extension (add optional kwarg):**

```python
# bot/gateway.py
async def _call_langgraph(
    thread_id: str,
    user_id: str,
    *,
    input: dict | None = None,
    command: dict | None = None,
    user_profile: dict | None = None,
    daily_log_today: list[dict] | None = None,  # NEW
) -> dict:
    body: dict = {
        "assistant_id": ASSISTANT_ID,
        "context": {"user_id": user_id},
    }
    if user_profile:
        body["context"]["user_profile"] = user_profile
    if daily_log_today is not None:  # NEW — explicit None check; empty list is valid
        body["context"]["daily_log_today"] = daily_log_today
    ...
```

**`response_node` injection (mirror the existing `plan_section` block):**

```python
# src/agents/nodes/response_node.py
def _format_daily_log(logs: list[dict]) -> str:
    """Render today's logs as a markdown section for the system prompt.

    Always emits a section (never silent): explicit "nothing logged yet today"
    is a useful signal for the empty-log opener (audit Fix #5).
    """
    if not logs:
        return "\n\n## Today's Log\nNothing logged yet today."
    lines = ["\n\n## Today's Log"]
    for log in logs:
        # timestamp is already Israel local from _serialize_log
        ts = log.get("timestamp") or ""
        amount = log.get("amount_g", 0)
        cals = log.get("calories", 0)
        protein = log.get("protein", 0)
        carbs = log.get("carbs", 0)
        fat = log.get("fat", 0)
        original = log.get("original_text") or ""
        lines.append(
            f"- {ts} — {original or f'{amount}g'} — "
            f"{cals:.0f} kcal, {protein:.1f}g protein, {carbs:.1f}g carbs, {fat:.1f}g fat"
        )
    return "\n".join(lines)
```

Call it in `response_node` alongside `plan_section`:

```python
plan = profile.get("nutrition_plan")
plan_section = (
    f"\n\n## User Nutrition Plan\n{plan}"
    if plan
    else "\n\n## User Nutrition Plan\nNo plan set for this user yet."
)

daily_log = context.daily_log_today or []
log_section = _format_daily_log(daily_log)

# ... existing json_context build ...

system_message = SystemMessage(
    content=(
        f"Current time: {now_str}\n\n"
        f"{_SYSTEM_PROMPT}"
        f"\n\n---\n## User Profile\n"
        f"- Name: {profile.get('name', 'Unknown')}\n"
        f"- Age: {profile.get('age', 'Unknown')}\n"
        f"- Gender: {profile.get('gender', 'Unknown')}\n"
        f"- Height: {profile.get('height_cm', 'Unknown')}cm"
        f"{plan_section}"
        f"{log_section}"  # NEW — between plan and context JSON
        f"\n\n---\nContext JSON:\n```json\n{json_context}\n```"
    )
)
```

**Unit test pattern (mirror `TestCurrentTimeStr` from Fix #1):**

Place the new test class in the same file `tests/unit/test_response_node.py`, style matches `TestCurrentTimeStr` (added this session).

**Integration test pattern (mirror `tests/integration/test_user_profile_service.py`):**

Use `async_test_db_session` fixture, `TEST_USER_A`, insert via `create_log_entry`, assert via the new `get_todays_logs_serialized` helper. DO NOT modify `_patch_session` — not needed for helpers that accept `session` directly.

---

## IMPLEMENTATION PLAN

### Phase 1 — Service Layer (Bug 2 + `get_todays_logs_serialized`)

Fix `_serialize_log` to emit Israel-local ISO strings. Add `get_todays_logs_serialized` helper.

**Tasks:**
- Import `USER_TIMEZONE` in `daily_log_service.py`.
- Modify `_serialize_log` to `.astimezone(USER_TIMEZONE).isoformat()`.
- Add `get_todays_logs_serialized(session, user_id) -> list[dict]` helper.

### Phase 2 — Context Schema Extension

Add `daily_log_today: list[dict]` with default empty list.

**Tasks:**
- Add field to `ContextSchema` dataclass using `field(default_factory=list)`.

### Phase 3 — Bot Wiring (per-message fetch + context body)

Fetch today's log fresh every message (NOT cached). Pass through to `_call_langgraph`.

**Tasks:**
- Add `_load_todays_log(user_id)` helper below `_load_user_profile`.
- Add `daily_log_today: list[dict] | None = None` kwarg to `_call_langgraph`.
- Inject into `body["context"]` when provided (explicit None check; empty list IS valid).
- In `_handle_authenticated_message`, fetch `todays_log` after profile is loaded and pass to both `_call_langgraph` call sites (interrupted-resume and new-input).

### Phase 4 — Response Node Injection

Private formatter + system prompt wiring.

**Tasks:**
- Add `_format_daily_log(logs)` private helper (module-level) that always renders a section (empty log → explicit "nothing logged yet today").
- Read `context.daily_log_today` in `response_node`, call formatter, splice into `SystemMessage` between `plan_section` and `Context JSON`.

### Phase 5 — Tests

Unit coverage for serializer, formatter, and render. Integration coverage for the service helper.

**Tasks:**
- Unit: `_serialize_log` converts UTC → Israel (deterministic, known UTC instant).
- Unit: `_format_daily_log` renders both populated and empty cases.
- Unit: `response_node` system message contains log section (populated and empty).
- Integration: `get_todays_logs_serialized` returns today's logs only, serialized with Israel ISO.

### Phase 6 — Follow-up Task + Commit Log

Document Bug 1 as a maintenance task. Write a commit log so PR review has PR-level context.

**Tasks:**
- Append Bug 1 follow-up to `brain/TASKS.md` Maintenance tier with a concrete description.
- Write commit log at `commit_logs/<timestamp>_feat-daily-log-injection-and-israel-tz.md` summarizing the changes, test counts, and next steps (mirrors PR #21 log).

### Phase 7 — Manual Smoke Test

Before considering the feature done, exercise it against a real bot + Studio.

**Tasks:**
- Run `langgraph dev`, open Studio, check a CHITCHAT turn: system prompt contains `## Today's Log` section.
- Run bot locally with `POLLING_MODE=true`, ask "status so far today?" with an empty log and with a non-empty log. Verify both cases read correctly and timestamps show Israel local.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### UPDATE `src/services/daily_log_service.py`

- **IMPLEMENT**:
  1. Add `from src.config import USER_TIMEZONE` to the imports block (after existing imports).
  2. Modify `_serialize_log` to convert `log.timestamp` to Israel local before `.isoformat()` — see Patterns block above for the exact body.
  3. Add a new async function `get_todays_logs_serialized(session, user_id) -> list[dict]` after `get_logs_by_date_range`. Body per the Patterns block. Include the KNOWN LIMITATION docstring about Bug 1.
- **PATTERN**: `src/services/daily_log_service.py` lines 108-128 (`get_logs_by_date`), lines 162-175 (`_serialize_log`).
- **IMPORTS**: `from src.config import USER_TIMEZONE`. No other new imports — `datetime` already imported.
- **GOTCHA**: `log.timestamp` returned by asyncpg from a `DateTime(timezone=True)` column is an **aware** datetime in UTC. `.astimezone(USER_TIMEZONE)` re-expresses without changing the instant. Do NOT use `.replace(tzinfo=USER_TIMEZONE)` — that would SHIFT the absolute moment by 3 hours (wrong direction, and silently).
- **GOTCHA**: The new helper uses `get_logs_by_date` (date-based DB query), which has Bug 1 near midnight. That's intentional — Bug 1 is explicitly out of scope.
- **VALIDATE**: `uv run python -c "from src.services.daily_log_service import _serialize_log, get_todays_logs_serialized; print('ok')"`

### UPDATE `src/context.py`

- **IMPLEMENT**: Add `daily_log_today: list[dict] = field(default_factory=list)` to `ContextSchema` dataclass, directly after the `user_profile` field.
- **PATTERN**: `src/context.py` line 43 (`user_profile` field pattern). Mutable default MUST use `field(default_factory=...)`.
- **IMPORTS**: None new — `field` already imported.
- **GOTCHA**: Do NOT use `= []` as a default — Python dataclass will raise `ValueError: mutable default...`.
- **GOTCHA**: Do NOT add `daily_log_today` to `DEFAULT_DEV_PROFILE` — it's a top-level `ContextSchema` field, NOT part of the profile dict.
- **VALIDATE**: `uv run python -c "from src.context import ContextSchema; c = ContextSchema(); print(c.daily_log_today); assert c.daily_log_today == []"`

### UPDATE `bot/gateway.py`

- **IMPLEMENT**:
  1. Add `from src.services.daily_log_service import get_todays_logs_serialized` to the existing imports block (next to `get_user_profile`).
  2. Add `_load_todays_log(user_id)` helper beneath `_load_user_profile` (see Patterns block for body).
  3. Extend `_call_langgraph` signature with `daily_log_today: list[dict] | None = None` kwarg. In the body construction, after the `user_profile` injection, add:
     ```python
     if daily_log_today is not None:
         body["context"]["daily_log_today"] = daily_log_today
     ```
     Use `is not None` — empty list is a valid, meaningful value.
  4. In `_handle_authenticated_message`, after `session["user_profile"]` is ensured (around line 295), add:
     ```python
     todays_log = await _load_todays_log(user_id)
     ```
  5. Pass `daily_log_today=todays_log` to BOTH `_call_langgraph` call sites — the `command={"resume": ...}` branch (line 302) AND the `input={...}` branch (line 308).
- **PATTERN**: `bot/gateway.py` lines 204-207 (`_load_user_profile` pattern), lines 90-117 (`_call_langgraph` signature + body), lines 293-313 (per-message handler).
- **IMPORTS**: `from src.services.daily_log_service import get_todays_logs_serialized`.
- **GOTCHA**: Do NOT add `daily_log_today` to `SessionData` TypedDict. The log is intentionally NOT cached on the session.
- **GOTCHA**: `_handle_authenticated_message` has TWO `_call_langgraph` call sites (resume branch + new-input branch). Both must pass `daily_log_today`. Missing one creates a silent bug where the log is injected on new messages but not on HITL-resume turns.
- **VALIDATE**: `uv run ruff check bot/gateway.py`

### UPDATE `src/agents/nodes/response_node.py`

- **IMPLEMENT**:
  1. Add a new module-level private function `_format_daily_log(logs: list[dict]) -> str` — see Patterns block for body. Place it after `_current_time_str` (added in Fix #1 this session) and before `_serialize_date`.
  2. Inside `response_node()`, after `plan_section` is built and before the `json_context = _build_context(state)` line, compute:
     ```python
     daily_log = context.daily_log_today if context.daily_log_today is not None else []
     log_section = _format_daily_log(daily_log)
     ```
  3. Splice `f"{log_section}"` into the `SystemMessage.content` f-string — directly AFTER `f"{plan_section}"` and BEFORE the `f"\n\n---\nContext JSON:\n```json\n..."` line.
- **PATTERN**: `src/agents/nodes/response_node.py` lines 26-34 (`_current_time_str` helper style), lines 98-122 (existing system-message construction).
- **IMPORTS**: None new.
- **GOTCHA**: `context.daily_log_today` may be `None` in the `context is None` edge case already handled at line 92 (`context = runtime.context if runtime.context is not None else ContextSchema()`). Since the default factory is `list`, fresh `ContextSchema()` gives `[]`, not `None`. But be defensive in the node with `if context.daily_log_today is not None else []` in case external callers pass a partially-constructed dataclass.
- **GOTCHA**: `_format_daily_log` MUST always return a non-empty string (with "Nothing logged yet today" for empty lists). This is deliberate — the F1 empty-log opener (fixed in a later audit workstream) depends on the LLM seeing an explicit empty signal.
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v` (existing tests must still pass; new tests added in the next step).

### UPDATE `tests/unit/test_response_node.py`

- **IMPLEMENT**:
  1. Import `_format_daily_log` from `src.agents.nodes.response_node` in the existing import block.
  2. Add a new test class `TestFormatDailyLog` (mirror `TestCurrentTimeStr` style — added this session at lines 152-170):
     - `test_empty_log_renders_explicit_empty_section` — asserts `_format_daily_log([])` contains `"## Today's Log"` and `"Nothing logged yet today"`.
     - `test_populated_log_renders_items` — asserts each log's `original_text` and macro numbers appear, and the `## Today's Log` header is present.
  3. Add two new tests to `TestResponseNode`:
     - `test_daily_log_section_shown_when_log_present` — build a runtime with `ContextSchema(user_id=TEST_USER_A, user_profile=..., daily_log_today=[{...serialized log dict with Israel-ISO timestamp...}])`, invoke node, assert the SystemMessage content contains the log's `original_text` substring AND the `## Today's Log` header.
     - `test_daily_log_empty_section_shown_when_log_empty` — build a runtime with `daily_log_today=[]`, invoke, assert `## Today's Log` + `"Nothing logged yet today"` appear.
- **PATTERN**: `tests/unit/test_response_node.py` lines 152-170 (`TestCurrentTimeStr`), lines 327-348 (`test_plan_injected_in_system_message` — exact shape for constructing a `MagicMock` runtime with a custom `ContextSchema`).
- **IMPORTS**: Extend the existing `from src.agents.nodes.response_node import (...)` block to include `_format_daily_log`.
- **GOTCHA**: When building the runtime in the new response_node tests, you MUST set `daily_log_today` on the `ContextSchema` directly — NOT inside `user_profile`.
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v`

### CREATE `tests/integration/test_daily_log_service.py`

- **IMPLEMENT**: Integration tests covering:
  1. **`_serialize_log` emits Israel local ISO** — arrange: `create_log_entry` with an aware UTC timestamp (e.g. `datetime(2026, 4, 16, 19, 11, tzinfo=timezone.utc)`); act: fetch via `get_logs_by_date` and call `_serialize_log`; assert: serialized `timestamp` string contains `"+03:00"` (IDT offset) and the HH:MM is `22:11`.
  2. **`get_todays_logs_serialized` returns only today's logs** — arrange: `create_log_entry` with today-Israel timestamp and a second entry from yesterday; act: call `get_todays_logs_serialized`; assert: list length == 1, contains today's log only.
  3. **`get_todays_logs_serialized` returns empty for new user** — arrange: no log entries for a fresh user; act: call helper; assert: returns `[]`.
  4. **`get_todays_logs_serialized` is user-scoped** — arrange: `create_log_entry` for `TEST_USER_A` today and another for `TEST_USER_B` today; act: call helper for `TEST_USER_A`; assert: only `TEST_USER_A`'s log returns.
- **PATTERN**: `tests/integration/test_user_profile_service.py` (entire file) — fixture usage, class structure, AAA docstrings.
- **IMPORTS**:
  ```python
  from datetime import datetime, timedelta, timezone
  from tests.conftest import TEST_USER_A, TEST_USER_B
  from src.services.daily_log_service import (
      create_log_entry,
      get_todays_logs_serialized,
      _serialize_log,
      get_logs_by_date,
  )
  from src.config import USER_TIMEZONE
  ```
- **GOTCHA**: When asserting Israel ISO offset, Israel observes both `+02:00` (IST, winter) and `+03:00` (IDT, summer). Pick a UTC instant inside IDT (April is IDT) for deterministic testing. Do NOT assert on the raw offset string if you pick a date in the DST transition window.
- **GOTCHA**: For the user-scoped test, `TEST_USER_B` is `e2e@test.fitpal.bot` — already exists in `auth.users`. The `async_test_db_session` fixture rolls back everything, so no cleanup concern.
- **VALIDATE**: `uv run pytest tests/integration/test_daily_log_service.py -v`

### UPDATE `brain/TASKS.md`

- **IMPLEMENT**: Append to the Maintenance tier a new unchecked task:
  ```markdown
  - [ ] Fix near-midnight "today" boundary in `get_logs_by_date` — `func.date(timestamp) == target_date` evaluates in the DB session's timezone (UTC on Supabase), so logs made 00:00–03:00 Israel local fall on previous UTC date and get missed. Replace with a timestamp range `>= start_utc AND < end_utc` computed from `USER_TIMEZONE`. Affects `stats_lookup_node` and `get_todays_logs_serialized`. — [[brain/planning/bot-ux-audit-2026-04-17|source]]
  ```
- **GOTCHA**: This task goes in Maintenance, not in `Important — Real User Quality`. It's an edge-case correctness fix, not a user-quality driver at POC scale (midnight dogfooding is rare).
- **VALIDATE**: `grep -n "near-midnight" brain/TASKS.md` returns the new line.

### CREATE `commit_logs/<YYYY-MM-DD>_<HH-MM-SS>_feat-daily-log-injection-and-israel-tz.md`

- **IMPLEMENT**: Write a commit log following the structure of `commit_logs/2026-04-13_20-15-00_feat-nutrition-plan-injection.md`. Sections:
  - Header (date, branch, commit placeholder or hash)
  - Changes subsections: Service Layer, Runtime Context, Bot Gateway, Agent Integration, Tests
  - Validation (test counts, commands run)
  - Next Steps (Fix #5 empty-log opener is now unblocked by this change — note that in the "Next Steps" list)
  - Out of scope / follow-ups (Bug 1 linked to the new TASKS.md line)
- **PATTERN**: `commit_logs/2026-04-13_20-15-00_feat-nutrition-plan-injection.md` (mirror of PR #21's log).
- **GOTCHA**: Do NOT commit this log until the code changes are committed in the same commit — there's a tracked Maintenance task to co-commit logs (see `brain/planning/session-takeaways-2026-04-12`).

---

## TESTING STRATEGY

### Unit Tests

**`tests/unit/test_response_node.py`** — extend existing file, do NOT create a new one:
- `TestFormatDailyLog::test_empty_log_renders_explicit_empty_section`
- `TestFormatDailyLog::test_populated_log_renders_items`
- `TestResponseNode::test_daily_log_section_shown_when_log_present`
- `TestResponseNode::test_daily_log_empty_section_shown_when_log_empty`

All use the existing `_make_state`, `@patch("...get_llm_for_node")`, and `ContextSchema`-based runtime fixtures.

### Integration Tests

**`tests/integration/test_daily_log_service.py`** — new file:
- `Test_SerializeLog_IsraelLocalTimestamp::test_aware_utc_stored_log_serializes_as_israel_iso`
- `TestGetTodaysLogsSerialized::test_returns_only_todays_logs`
- `TestGetTodaysLogsSerialized::test_returns_empty_list_for_new_user`
- `TestGetTodaysLogsSerialized::test_scopes_by_user_id`

Uses `async_test_db_session` fixture (transaction-rolled-back against real Supabase test DB).

### Edge Cases

- Empty log list (fresh user / new day): section must still render with explicit "Nothing logged yet today" — do NOT omit.
- Log entry where `original_text` is `None`: formatter falls back to `f"{amount_g}g"`.
- `context.daily_log_today` is `None` (defensive default): node treats as empty list, does not crash.
- HITL interrupt resume turn: `daily_log_today` still injected (both `_call_langgraph` call sites).
- Logs with float macros ending in `.0` (e.g. `0.0` carbs): `f"{x:.1f}g"` format keeps output readable.
- DST transition (Israel switches `Asia/Jerusalem` in late March / late October): `astimezone(USER_TIMEZONE)` handles this automatically — no manual offset math anywhere in the code.

### Gateway tests

If `tests/unit/test_gateway.py` already has patterns for mocking the langgraph HTTP call, add one test asserting `daily_log_today` is present in the JSON body. If no such pattern exists, skip — the integration test on the service helper covers the DB correctness, and the manual smoke test covers the end-to-end wire. Do NOT invent a new gateway-test pattern.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

```bash
uv run ruff check src/services/daily_log_service.py src/context.py bot/gateway.py src/agents/nodes/response_node.py
```

### Level 2: Unit Tests

```bash
uv run pytest tests/unit/test_response_node.py -v
uv run pytest tests/unit/ -q
```

Expect: all 122+ existing unit tests pass (Fix #1 brought count to 122; this fix adds 4 new response_node tests → 126 expected).

### Level 3: Integration Tests

```bash
uv run pytest tests/integration/test_daily_log_service.py -v
uv run pytest tests/integration/ -q
```

Expect: new test file's tests pass + all existing integration tests pass (no regressions in `stats_node` / `query_food_logs` consumers, since the serializer change is semantically correct and tests that were asserting on raw UTC would be surfacing the bug — confirm expected ISO format matches Israel, update existing assertions if any compare timestamp strings directly).

### Level 4: Graph-API Smoke (optional for this fix, but recommended)

```bash
uv run pytest tests/graph_api/ -v -s
```

Expect: existing E2E flows pass. This fix doesn't change graph edges/nodes, but validates the context-body path end-to-end on a real server.

### Level 5: Manual Validation

1. **Studio path**: `uv run langgraph dev`, open Studio, start a new conversation. Inspect the run's input → confirm `context.daily_log_today` appears (even as `[]`). Send "what did I eat today?" and verify the AIMessage doesn't gaslight.
2. **Bot path (empty log)**: start bot locally with `POLLING_MODE=true`, passphrase-auth, ask "מה אכלתי היום?" — bot should say nothing was logged today, in a coach voice (F1 full fix still requires prompt engineering Workstream item #5 — but the gaslighting wording should disappear because the prompt no longer relies on the LLM's guess).
3. **Bot path (populated log)**: log a food via the bot, confirm via HITL, then ask "what's my status?" — bot should reference the just-logged item explicitly, and the time shown should be Israel local (22:00, not 19:00).
4. **Bug 2 verification**: inspect the Telegram reply — any time references from the LLM should be in Israel local time.

---

## ACCEPTANCE CRITERIA

- [ ] `ContextSchema` has `daily_log_today: list[dict]` field with `default_factory=list`
- [ ] `_serialize_log` outputs `timestamp` in Israel local ISO format (contains `+02:00` or `+03:00` depending on DST)
- [ ] `get_todays_logs_serialized(session, user_id)` helper exists, uses `USER_TIMEZONE`, returns `list[dict]`, scoped to today-in-Israel
- [ ] `bot/gateway.py::_load_todays_log` fetches fresh every call (NOT cached on `SessionData`)
- [ ] `_call_langgraph` accepts `daily_log_today` kwarg and includes it in `body["context"]` when not `None`
- [ ] BOTH `_call_langgraph` call sites (resume branch + new-input branch) pass `daily_log_today`
- [ ] `response_node` includes a `## Today's Log` section in the `SystemMessage` on every run (populated OR explicit empty)
- [ ] `_format_daily_log([])` returns a non-empty string containing "Nothing logged yet today"
- [ ] `_format_daily_log([log1, log2])` lists both items with Israel-local timestamps, original_text, and macros
- [ ] All existing 122 unit tests pass
- [ ] 4 new unit tests pass (`TestFormatDailyLog` × 2, new `TestResponseNode` × 2)
- [ ] All existing integration tests pass
- [ ] 4 new integration tests pass in `test_daily_log_service.py`
- [ ] `ruff check` passes on all modified files
- [ ] `brain/TASKS.md` Maintenance tier has new Bug 1 follow-up line
- [ ] `commit_logs/<timestamp>_feat-daily-log-injection-and-israel-tz.md` written
- [ ] Manual smoke test via dev bot confirms timestamps render in Israel local and empty-log case no longer gaslights

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit + integration)
- [ ] No linting errors
- [ ] Manual smoke confirms feature end-to-end
- [ ] Bug 1 follow-up task in `brain/TASKS.md`
- [ ] Commit log written
- [ ] All acceptance criteria met

---

## NOTES

### Design decisions made in the planning session

- **Option A (fetch every message, no caching for the log)** chosen over Option B (cache + invalidate after commits). Rationale: Option B's silent-failure mode (stale log → silently wrong coaching) outweighs the tiny DB-query savings. LLM call dominates latency; one indexed DB read per turn is negligible.
- **Option B placement (service-layer serialization + response_node formatter)** chosen over Option A (raw ORM in context) or Option C (pre-formatted string in context). Rationale: keeps ORM out of context (serializable dict is web-safe), fixes Bug 2 at a single point that benefits all downstream consumers (`stats_node`, `query_food_logs` tool, new injection), and keeps presentation decisions local to the only consumer (`response_node`).
- **`list[dict]` shape over `list[QueriedLog]`** chosen because `QueriedLog` is a runtime TypedDict that provides no validation guarantees anyway. Plain `list[dict]` matches what `_serialize_log` already returns and what `query_food_logs` already emits.
- **Always render the section** (populated or "Nothing logged yet today"), never silently omit. Rationale: the F1 empty-log opener (Workstream 2 item #5 in the audit) depends on the LLM having an explicit empty-state signal to reason over.
- **Bug 1 out of scope.** The `func.date()` near-midnight comparison bug affects `stats_node` and this new path alike, but only bites 00:00–03:00 Israel local — rare in dogfooding. Tracked as a Maintenance task.

### Future work unblocked by this fix

- **Audit Fix #5 (empty-log coach-voice opener)** — depends on Fix #1 (done this session) AND this Fix #2. Now unblocked.
- **Audit Fix #6 (budget reasoning template)** — depends on this Fix #2 AND Fix #3 (`plan_category`). Half-unblocked.
- **POC blocker: Plan vs actual reasoning** — the data is now available; the reasoning is a prompt-engineering task that follows.

### Known limitations preserved (not introduced)

- Bot session cache for `user_profile` still has a 30-min staleness window when `set_plan.py` updates a plan mid-session. This fix does NOT address that (see `brain/learnings/pr21-nutrition-plan-review.md`).
- Token budget: ~500 tokens/turn added for a full day's log. Acceptable at POC scale (single-user dogfood + small friend cohort).

**Confidence Score**: 9/10 — pattern is well-established from PR #21, no new dependencies, all boundaries (bot → context → node) have concrete prior art in the codebase. The 1 point of risk is the interplay between Bug 2's serializer change and any existing integration tests that may assert on UTC ISO strings — implementation should grep for `isoformat` / `+00:00` in the test suite and update assertions to Israel local as a pre-flight check.
