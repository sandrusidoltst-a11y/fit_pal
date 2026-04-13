# Feature: Per-User Nutrition Plan Injection

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files.

## Feature Description

Add a `nutrition_plan` text field to each user's profile. The coach (Dolev) writes the plan as a markdown/text document and uploads it via a local script. The agent loads the plan at runtime and injects it into the `response_node` system prompt, so it can give contextual advice ("you have 40g protein left"), enforce coaching principles, and reference the trainee's specific meal structure and food bank.

Also inject the current time into the `response_node` system prompt (same pattern already used in `input_node`), and update the input parser prompt to correctly route plan-vs-actual questions.

## User Story

As Dolev (the coach),
I want to set a nutrition plan for each trainee,
So that the FitPal agent can give personalized coaching based on their specific plan.

As a trainee,
I want the bot to know my plan targets,
So that it can tell me how much I have left, flag timing issues, and guide my food choices.

## Problem Statement

The agent currently knows coaching principles (from the rewritten system prompt) but has no per-user plan. It can't answer "how many carbs do I have left?" correctly without knowing the trainee's daily targets. It also doesn't know the current time, which is needed for time-aware feedback.

## Solution Statement

1. Add `nutrition_plan: TEXT` column (nullable) to `UserProfile` model and Supabase.
2. Update `get_user_profile` service to return `nutrition_plan` in the dict.
3. Update `ContextSchema.UserProfile` TypedDict to include `nutrition_plan`.
4. Update `gateway.py` to include `nutrition_plan` when loading the profile into session context.
5. Update `response_node.py` to inject the plan text and current time into the system message.
6. Update `prompts/input_parser.md` to route plan-vs-actual questions to `QUERY_DAILY_STATS`.
7. Create `src/scripts/set_plan.py` — coach script to upload a plan file for a user.

## Feature Metadata

**Feature Type**: Enhancement
**Estimated Complexity**: Medium
**Primary Systems Affected**: `src/models.py`, `src/services/user_profile_service.py`, `src/context.py`, `src/agents/nodes/response_node.py`, `bot/gateway.py`, `prompts/input_parser.md`
**Dependencies**: None — no new packages needed.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

- `src/models.py` (lines 66-84) — UserProfile ORM model. Uses SQLAlchemy 2.0+ `Mapped[type]` style. Add `nutrition_plan` as `Mapped[Optional[str]]` with `nullable=True`.
- `src/services/user_profile_service.py` (lines 43-60) — `get_user_profile` returns a plain dict, not an ORM object. The dict keys match exactly what gets put in `ContextSchema`. Must add `nutrition_plan` key here.
- `src/context.py` (lines 23-48) — `UserProfile` TypedDict (runtime, not ORM) and `ContextSchema` dataclass. `total=False` means all fields are optional at runtime. Add `nutrition_plan: str` to the TypedDict and `DEFAULT_DEV_PROFILE`.
- `src/agents/nodes/response_node.py` (lines 81-118) — Where to inject plan and current time. Profile section built at lines 94-100, system message assembled at lines 106-108. Mirror the `input_node.py` pattern for time injection.
- `src/agents/nodes/input_node.py` (lines 33-35) — **Already has the current time injection pattern**: `datetime.now().strftime("%Y-%m-%d %H:%M:%S")` prepended to system prompt. Mirror this in `response_node`.
- `bot/gateway.py` (lines 189-258) — `_load_user_profile()` (line 202) calls `get_user_profile` service and returns dict. Session caches `user_profile` dict (line 249). `_call_langgraph()` passes `user_profile` in `body["context"]` (lines 101-104). Add `nutrition_plan` to both cache and context.
- `src/scripts/ingest_simple_db.py` — Script structure reference. Uses `sys.path.append`, `load_dotenv`, direct SQLAlchemy engine setup, `asyncio.run()` entry point.
- `prompts/input_parser.md` (lines 14-18) — `QUERY_DAILY_STATS` definition. Add plan-vs-actual examples.
- `tests/unit/test_response_node.py` — Test pattern. Uses `_make_state()` helper, mocks LLM via `@patch("src.agents.nodes.response_node.get_llm_for_node")`, inspects SystemMessage content.
- `tests/integration/test_food_service.py` (lines 1-60) — Integration test pattern: `_patch_session()` async context manager, patches `get_async_db_session`.

### New Files to Create

- `src/scripts/set_plan.py` — Coach CLI script: reads a plan file and sets `nutrition_plan` on a user's profile in Supabase.
- `tests/integration/test_user_profile_service.py` — Integration tests for updated `get_user_profile` (verifies `nutrition_plan` returned) and for `set_nutrition_plan` service function.

### Patterns to Follow

**SQLAlchemy Mapped column (nullable optional):**
```python
nutrition_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```
Follow the same style as `src/models.py` line 77 (`Optional[datetime]`).

**Service returns plain dict:**
```python
return {
    "name": profile.name,
    "height_cm": profile.height_cm,
    "age": profile.age,
    "gender": profile.gender,
    "nutrition_plan": profile.nutrition_plan,  # None if not set
}
```

**Time injection (from `input_node.py` lines 33-35):**
```python
from datetime import datetime
now_str = datetime.now().strftime("%A, %Y-%m-%d %H:%M")
```

**Bot session profile dict (from `gateway.py` line 249):**
```python
session["user_profile"] = {
    "name": name,
    "height_cm": ...,
    "age": ...,
    "gender": ...,
    "nutrition_plan": profile.get("nutrition_plan"),  # pass through from DB
}
```

**Script entry point pattern (from `ingest_simple_db.py`):**
```python
import asyncio, sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from dotenv import load_dotenv
load_dotenv()

async def main():
    ...

if __name__ == "__main__":
    asyncio.run(main())
```

---

## IMPLEMENTATION PLAN

### Phase 1: DB + Service Layer

Add `nutrition_plan` to the DB model and update the service layer to read/write it.

### Phase 2: Runtime Context Wiring

Add `nutrition_plan` to `ContextSchema` so it flows from the bot through LangGraph to nodes.

### Phase 3: Agent Integration

Inject the plan and current time into `response_node`'s system prompt.

### Phase 4: Input Parser Update

Update the input parser prompt to route plan-vs-actual questions correctly.

### Phase 5: Coach Upload Script

Create `set_plan.py` for Dolev to upload plans per user.

### Phase 6: Tests + Validation

---

## STEP-BY-STEP TASKS

### UPDATE `src/models.py`

- **ADD** `nutrition_plan` field to `UserProfile` class (after line 76):
  ```python
  nutrition_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  ```
- **IMPORTS**: Add `Text` to the SQLAlchemy column type imports at the top of the file.
- **GOTCHA**: Do NOT use `create_all()` or `drop_all()`. The column must be added via Supabase SQL migration separately.
- **VALIDATE**: `uv run python -c "from src.models import UserProfile; print('ok')"`

### MIGRATE Supabase

- **RUN** this SQL in Supabase SQL Editor (Dashboard → SQL Editor):
  ```sql
  ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS nutrition_plan TEXT;
  ```
- **VALIDATE**: Check column appears in Supabase Table Editor under `user_profiles`.

### UPDATE `src/services/user_profile_service.py`

- **ADD** new service function `set_nutrition_plan` after `get_user_profile`:
  ```python
  async def set_nutrition_plan(
      session: AsyncSession,
      user_id: str,
      nutrition_plan: str,
  ) -> None:
      """Set or update the nutrition plan for a user."""
      stmt = select(UserProfile).where(UserProfile.user_id == uuid_mod.UUID(user_id))
      result = await session.execute(stmt)
      profile = result.scalar_one_or_none()
      if profile is None:
          raise ValueError(f"No profile found for user_id={user_id}")
      profile.nutrition_plan = nutrition_plan
      await session.commit()
      logger.info("Nutrition plan updated", user_id=user_id)
  ```
- **UPDATE** `get_user_profile` return dict to include `nutrition_plan`:
  ```python
  return {
      "name": profile.name,
      "height_cm": profile.height_cm,
      "age": profile.age,
      "gender": profile.gender,
      "nutrition_plan": profile.nutrition_plan,
  }
  ```
- **PATTERN**: `src/services/user_profile_service.py` lines 43-60
- **VALIDATE**: `uv run pytest tests/integration/test_user_profile_service.py -v` (after creating tests)

### UPDATE `src/context.py`

- **UPDATE** `UserProfile` TypedDict to add `nutrition_plan`:
  ```python
  class UserProfile(TypedDict, total=False):
      name: str
      height_cm: float
      age: int
      gender: str
      nutrition_plan: str  # optional — None if no plan set
  ```
- **UPDATE** `DEFAULT_DEV_PROFILE` to include a placeholder plan for Studio:
  ```python
  DEFAULT_DEV_PROFILE: dict = {
      "name": "Dev User",
      "height_cm": 175.0,
      "age": 25,
      "gender": "male",
      "nutrition_plan": "Daily targets: 1600 kcal, 120g protein, 150g carbs, 50g fat.",
  }
  ```
- **GOTCHA**: `total=False` means `nutrition_plan` is optional — nodes must use `.get("nutrition_plan")` not direct access.
- **VALIDATE**: `uv run python -c "from src.context import ContextSchema, DEFAULT_DEV_PROFILE; print(DEFAULT_DEV_PROFILE)"`

### UPDATE `bot/gateway.py`

- **UPDATE** `_load_user_profile()` — no change needed, it returns the full dict from `get_user_profile` already.
- **UPDATE** `_handle_onboarding()` session cache (line ~249) to pass through `nutrition_plan` from the existing profile if it exists. When onboarding completes for an existing user, fetch their plan from DB and include it:
  ```python
  existing_plan = existing_profile.get("nutrition_plan") if existing_profile else None
  session["user_profile"] = {
      "name": name,
      "height_cm": session["onboarding_data"]["height_cm"],
      "age": session["onboarding_data"]["age"],
      "gender": session["onboarding_data"]["gender"],
      "nutrition_plan": existing_plan,
  }
  ```
- **GOTCHA**: The bot session caches `user_profile` in memory. When `set_plan.py` updates the DB, the cached session won't refresh until the user's session expires (30 min) or bot restarts. This is acceptable for POC — plan updates take effect on next session.
- **VALIDATE**: Run bot locally and verify `user_profile` dict in logs includes `nutrition_plan`.

### UPDATE `src/agents/nodes/response_node.py`

- **ADD** current time injection (mirror of `input_node.py` lines 33-35):
  ```python
  from datetime import datetime  # already imported
  
  # In response_node(), before building system_message:
  now_str = datetime.now().strftime("%A, %Y-%m-%d %H:%M")
  ```
- **UPDATE** system message construction to inject time and plan:
  ```python
  plan = profile.get("nutrition_plan")
  plan_section = f"\n\n## User Nutrition Plan\n{plan}" if plan else "\n\n## User Nutrition Plan\nNo plan set for this user yet."
  
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
          f"\n\n---\nContext JSON:\n```json\n{json_context}\n```"
      )
  )
  ```
- **PATTERN**: `src/agents/nodes/input_node.py` lines 33-35, `response_node.py` lines 94-108
- **GOTCHA**: `_SYSTEM_PROMPT` is loaded at import time (line 16-25). Time must be injected at call time (inside the async function), not at module level.
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v`

### UPDATE `prompts/input_parser.md`

- **UPDATE** `QUERY_DAILY_STATS` description to add plan-vs-actual examples:
  ```markdown
  - **QUERY_DAILY_STATS**: The user is asking about their nutrition stats, logs, or how their intake compares to their plan.
    - Examples: "How much protein have I eaten?", "Calories left?", "What did I eat yesterday?", "Stats for last 3 days", "How many carbs do I have left today?", "Am I on track?", "Did I hit my protein target?", "How much more can I eat?"
  ```
- **VALIDATE**: Run input parser eval notebook or manually test a few plan-vs-actual questions.

### CREATE `src/scripts/set_plan.py`

- **CREATE** script that reads a plan file and updates the user's `nutrition_plan` in Supabase:
  ```python
  """
  Coach CLI script: set a nutrition plan for a user.

  Usage:
      uv run python src/scripts/set_plan.py <user_id> <plan_file.txt>

  Example:
      uv run python src/scripts/set_plan.py fbeeb45f-d728-4c7c-9e6d-7b9b41685da7 plans/brother_plan.txt
  """
  import asyncio
  import sys
  import os

  sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

  from dotenv import load_dotenv
  load_dotenv()

  from src.database import get_async_db_session
  from src.services.user_profile_service import set_nutrition_plan


  async def main(user_id: str, plan_file: str) -> None:
      with open(plan_file, "r", encoding="utf-8") as f:
          plan_text = f.read()

      async with get_async_db_session() as session:
          await set_nutrition_plan(session, user_id, plan_text)
          print(f"Plan updated for user {user_id} ({len(plan_text)} chars)")


  if __name__ == "__main__":
      if len(sys.argv) != 3:
          print("Usage: uv run python src/scripts/set_plan.py <user_id> <plan_file>")
          sys.exit(1)
      asyncio.run(main(sys.argv[1], sys.argv[2]))
  ```
- **PATTERN**: `src/scripts/ingest_simple_db.py` entry point pattern
- **VALIDATE**: `uv run python src/scripts/set_plan.py --help` (should print usage and exit cleanly)

### CREATE `tests/integration/test_user_profile_service.py`

- **CREATE** integration tests covering:
  1. `get_user_profile` returns `nutrition_plan` field (None when unset)
  2. `set_nutrition_plan` updates the field correctly
  3. `get_user_profile` returns updated plan after `set_nutrition_plan`
- **PATTERN**: Mirror `tests/integration/test_food_service.py` — use `_patch_session()` context manager
- **VALIDATE**: `uv run pytest tests/integration/test_user_profile_service.py -v`

### UPDATE `tests/unit/test_response_node.py`

- **UPDATE** existing tests to assert system message includes current time prefix (`"Current time:"`)
- **ADD** test `test_plan_injected_in_system_message()`:
  - Create runtime with `user_profile` including `nutrition_plan`
  - Invoke `response_node`, inspect SystemMessage content
  - Assert plan text appears in system message
- **ADD** test `test_no_plan_shows_placeholder()`:
  - Create runtime with `user_profile` without `nutrition_plan`
  - Assert system message includes "No plan set" fallback
- **PATTERN**: `tests/unit/test_response_node.py` lines 155-225

---

## TESTING STRATEGY

### Unit Tests

- `tests/unit/test_response_node.py` — verify plan injection, time injection, no-plan fallback, existing tests still pass

### Integration Tests

- `tests/integration/test_user_profile_service.py` — verify `nutrition_plan` round-trip through service layer

### Manual Validation

1. Run `uv run python src/scripts/set_plan.py <dev_user_id> <plan_file>` and verify DB update
2. Start `langgraph dev`, log food in Studio, verify system prompt includes plan
3. Ask "how many carbs do I have left?" — verify routes to `QUERY_DAILY_STATS`, not `CHITCHAT`
4. Ask "am I on track today?" — verify same routing

---

## VALIDATION COMMANDS

```bash
# Syntax check
uv run ruff check src/models.py src/services/user_profile_service.py src/context.py src/agents/nodes/response_node.py src/scripts/set_plan.py

# Unit tests
uv run pytest tests/unit/test_response_node.py -v

# Integration tests
uv run pytest tests/integration/test_user_profile_service.py -v

# Full unit suite (no regressions)
uv run pytest tests/unit/ -v
```

---

## ACCEPTANCE CRITERIA

- [ ] `nutrition_plan` column exists in Supabase `user_profiles` table
- [ ] `get_user_profile` returns `nutrition_plan` field (None if unset)
- [ ] `set_nutrition_plan` service function updates the DB correctly
- [ ] `set_plan.py` script works end-to-end for dev user
- [ ] `response_node` system message includes current time
- [ ] `response_node` system message includes plan text when set, fallback when not
- [ ] "How many carbs do I have left?" routes to `QUERY_DAILY_STATS` in manual test
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] No regressions in existing `tests/unit/`

---

## NOTES

- **Training day vs non-training day** is noted as a future enhancement. Not in scope for this plan — the plan text can include training day guidance in free text, and the agent will interpret it contextually.
- **Session cache refresh**: When the coach updates a plan via `set_plan.py`, the bot's in-memory session cache won't reflect it until the session expires (30 min timeout). Acceptable for POC.
- **Hebrew support**: Already added to `prompts/response_generator.md` — the agent responds in the user's language.
- **Plan format**: No schema enforced — plain text or markdown, coach writes what makes sense. The agent reads it as-is.
- **Evals**: Run input parser eval after updating the prompt to verify routing changes don't break existing classifications.

**Confidence Score**: 9/10 — all patterns are well-established in the codebase, no new dependencies, the wiring path is clear end-to-end.
