# Feature: Fix Onboarding Trigger for Existing Users Without Profiles

The following plan should be complete, but validate documentation and codebase patterns before implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files.

## Feature Description

Fix the Telegram bot onboarding flow so that existing Supabase auth users who lack a `user_profiles` row are prompted to complete onboarding. Currently, onboarding only triggers when `is_new=True` (user doesn't exist in Supabase auth). Users created before the onboarding feature was added — or whose profile save failed — are treated as returning users and never get onboarded, causing the LangGraph agent to fall back to hardcoded `DEFAULT_DEV_PROFILE` defaults ("Dev User", age 25).

## User Story

As a returning Telegram user without a profile  
I want to be prompted to complete onboarding when I authenticate  
So that the agent knows my real name, height, age, and gender instead of showing defaults

## Problem Statement

The bot checks `is_new` (from `get_or_create_user`) to decide whether to trigger onboarding. This flag only reflects whether the Supabase **auth** user was just created. Users who existed before onboarding was added have `is_new=False` but no `user_profiles` row. The `ContextSchema` dataclass falls back to `DEFAULT_DEV_PROFILE` (name="Dev User", age=25, height=175cm) for these users, making the agent respond with wrong personal data.

## Solution Statement

After `get_or_create_user` returns, check whether the user has a profile in the DB via `_load_user_profile`. If no profile exists, trigger onboarding regardless of `is_new`. This is a minimal, targeted fix — one condition change in the registration flow plus updated tests.

## Feature Metadata

**Feature Type**: Bug Fix  
**Estimated Complexity**: Low  
**Primary Systems Affected**: `bot/gateway.py` (registration flow), `tests/unit/test_onboarding.py`  
**Dependencies**: None (uses existing `_load_user_profile` helper)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ BEFORE IMPLEMENTING

- `bot/gateway.py` (lines 355-388) — Registration flow with `is_new` check. **This is the code to modify.**
- `bot/gateway.py` (lines 202-205) — `_load_user_profile()` helper already exists, returns `dict | None`.
- `bot/gateway.py` (lines 362-370) — Session initialization with `onboarding_step` and `user_profile`.
- `bot/gateway.py` (lines 208-258) — `_handle_onboarding()` flow for reference.
- `src/services/user_profile_service.py` (lines 43-60) — `get_user_profile()` returns `None` when no row exists.
- `src/context.py` (lines 14-20) — `DEFAULT_DEV_PROFILE` that gets used when no profile is injected.
- `tests/unit/test_onboarding.py` — Existing onboarding tests. New test case needed here.

### New Files to Create

None.

### Relevant Documentation

None required — this is a straightforward conditional logic fix using existing helpers.

### Patterns to Follow

**Logging Pattern** (from gateway.py):
```python
logger.info("descriptive message", key=value, key2=value2)
```

**Test Pattern** (from test_onboarding.py):
```python
@patch("bot.gateway._create_thread", new_callable=AsyncMock, return_value="thread-new")
@patch("bot.gateway.get_or_create_user", new_callable=AsyncMock)
async def test_something(self, mock_get_or_create, mock_create_thread, mock_message):
    """
    arrange: ...
    act:     ...
    assert:  ...
    """
```

**Session helper** (from test_onboarding.py):
```python
def _onboarding_session(step="name"):
    return {
        "user_id": "uuid-new-user",
        "thread_id": "thread-onb",
        "last_activity": datetime.now(timezone.utc),
        "interrupted": False,
        "onboarding_step": step,
        "onboarding_data": {},
        "user_profile": None,
    }
```

---

## IMPLEMENTATION PLAN

### Phase 1: Fix Registration Flow

Modify the passphrase handler in `handle_message` to check for profile existence when `is_new=False`. If no profile exists, trigger onboarding.

### Phase 2: Update Tests

Add a new test case for the "existing user without profile" scenario. Update the existing "existing user skips onboarding" test to mock `_load_user_profile` returning a profile (making the skip behavior explicit).

---

## STEP-BY-STEP TASKS

### Task 1: UPDATE `bot/gateway.py` — Add profile check to registration flow

**Location**: `handle_message` function, lines 355-388.

**Current code** (lines 358-380):
```python
try:
    result = await get_or_create_user(chat_id)
    thread_id = await _create_thread()
    is_new = result.get("is_new", False)
    user_sessions[chat_id] = {
        "user_id": result["user_id"],
        "thread_id": thread_id,
        "last_activity": datetime.now(timezone.utc),
        "interrupted": False,
        "onboarding_step": "name" if is_new else None,
        "onboarding_data": {},
        "user_profile": None,
    }
    logger.info("User registered for chat_id=%s, is_new=%s", chat_id, is_new)
    if is_new:
        await message.answer(
            "Welcome to FitPal! Let's set up your profile."
        )
        await message.answer(ONBOARDING_QUESTIONS["name"])
    else:
        await message.answer(
            "Welcome back to FitPal! You can start logging food now."
        )
```

**New code** — after `is_new` is determined, load the profile and decide if onboarding is needed:
```python
try:
    result = await get_or_create_user(chat_id)
    thread_id = await _create_thread()
    is_new = result.get("is_new", False)

    # Check if existing user has a profile — trigger onboarding if missing
    existing_profile = None
    if not is_new:
        existing_profile = await _load_user_profile(result["user_id"])
    needs_onboarding = is_new or existing_profile is None

    user_sessions[chat_id] = {
        "user_id": result["user_id"],
        "thread_id": thread_id,
        "last_activity": datetime.now(timezone.utc),
        "interrupted": False,
        "onboarding_step": "name" if needs_onboarding else None,
        "onboarding_data": {},
        "user_profile": existing_profile,
    }
    logger.info(
        "User registered",
        chat_id=chat_id,
        is_new=is_new,
        needs_onboarding=needs_onboarding,
    )
    if needs_onboarding:
        await message.answer(
            "Welcome to FitPal! Let's set up your profile."
        )
        await message.answer(ONBOARDING_QUESTIONS["name"])
    else:
        await message.answer(
            "Welcome back to FitPal! You can start logging food now."
        )
```

**Key changes:**
1. After `is_new`, load profile via `_load_user_profile` for existing users.
2. `needs_onboarding = is_new or existing_profile is None` — triggers onboarding for profileless users.
3. `user_profile` in session is set to `existing_profile` (preloaded, avoids redundant DB call later).
4. Welcome message uses `needs_onboarding` instead of `is_new`.
5. Logging now includes `needs_onboarding` for debuggability.

- **GOTCHA**: `_load_user_profile` is async and can raise if DB is unreachable. The entire block is already inside `try/except Exception`, so failures are handled.
- **GOTCHA**: For `is_new=True` users, we skip the profile load (they can't have one yet). This avoids an unnecessary DB call.
- **VALIDATE**: `uv run pytest tests/unit/test_onboarding.py -v`

### Task 2: UPDATE `tests/unit/test_onboarding.py` — Add test for existing user without profile

**ADD** a new test in `TestOnboardingStart` class:

```python
@patch("bot.gateway._load_user_profile", new_callable=AsyncMock, return_value=None)
@patch("bot.gateway._create_thread", new_callable=AsyncMock, return_value="thread-no-profile")
@patch("bot.gateway.get_or_create_user", new_callable=AsyncMock)
async def test_existing_user_without_profile_starts_onboarding(
    self, mock_get_or_create, mock_create_thread, mock_load_profile, mock_message
):
    """
    arrange: user sends correct passphrase, get_or_create_user returns is_new=False,
             _load_user_profile returns None (no profile row).
    act:     handle_message processes the passphrase.
    assert:  session created with onboarding_step="name", welcome + name question sent.
    """
    mock_get_or_create.return_value = {
        "user_id": "uuid-no-profile",
        "access_token": "tok",
        "refresh_token": "ref",
        "is_new": False,
    }
    mock_message.text = gw.BOT_PASSPHRASE or "test-passphrase"
    with patch.object(gw, "BOT_PASSPHRASE", mock_message.text):
        await gw.handle_message(mock_message)

    session = gw.user_sessions[mock_message.chat.id]
    assert session["onboarding_step"] == "name"
    assert mock_message.answer.call_count == 2  # welcome + name question
```

**UPDATE** the existing `test_existing_user_skips_onboarding` test to mock `_load_user_profile` returning a profile, making the test explicit about why onboarding is skipped:

```python
@patch("bot.gateway._load_user_profile", new_callable=AsyncMock, return_value={"name": "Test", "height_cm": 170, "age": 25, "gender": "male"})
@patch("bot.gateway._create_thread", new_callable=AsyncMock, return_value="thread-existing")
@patch("bot.gateway.get_or_create_user", new_callable=AsyncMock)
async def test_existing_user_with_profile_skips_onboarding(
    self, mock_get_or_create, mock_create_thread, mock_load_profile, mock_message
):
    """
    arrange: user sends correct passphrase, get_or_create_user returns is_new=False,
             _load_user_profile returns a valid profile.
    act:     handle_message processes the passphrase.
    assert:  session created with onboarding_step=None, welcome back message sent,
             user_profile is preloaded.
    """
    mock_get_or_create.return_value = {
        "user_id": "uuid-existing",
        "access_token": "tok",
        "refresh_token": "ref",
        "is_new": False,
    }
    mock_message.text = gw.BOT_PASSPHRASE or "test-passphrase"
    with patch.object(gw, "BOT_PASSPHRASE", mock_message.text):
        await gw.handle_message(mock_message)

    session = gw.user_sessions[mock_message.chat.id]
    assert session["onboarding_step"] is None
    assert session["user_profile"] is not None
    assert session["user_profile"]["name"] == "Test"
    assert mock_message.answer.call_count == 1
```

- **PATTERN**: Mirror existing test structure from `test_new_user_starts_onboarding` (lines 54-74).
- **GOTCHA**: Mock decorator order matters — decorators are applied bottom-up, so the parameter order in the test method is: `mock_get_or_create`, `mock_create_thread`, `mock_load_profile`, `mock_message`.
- **VALIDATE**: `uv run pytest tests/unit/test_onboarding.py -v`

---

## TESTING STRATEGY

### Unit Tests

All changes are in `tests/unit/test_onboarding.py`. Three test cases cover the registration flow:

1. **New user** → `is_new=True` → onboarding starts (existing test, unchanged)
2. **Existing user WITH profile** → `is_new=False`, profile loaded → onboarding skipped (updated existing test)
3. **Existing user WITHOUT profile** → `is_new=False`, profile is None → onboarding starts (new test)

### Edge Cases

- `_load_user_profile` raising an exception: covered by existing `try/except Exception` in `handle_message`. No new test needed — the registration failure test already covers this pattern.
- New user never calls `_load_user_profile`: verified by the `is_new=True` test not mocking `_load_user_profile`.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style
```bash
uv run ruff check bot/gateway.py tests/unit/test_onboarding.py
```

### Level 2: Unit Tests
```bash
uv run pytest tests/unit/test_onboarding.py -v
```

### Level 3: Full Unit Suite
```bash
uv run pytest tests/unit/ -v
```

---

## ACCEPTANCE CRITERIA

- [ ] Existing Supabase auth users without a `user_profiles` row are prompted to complete onboarding
- [ ] Existing users WITH a profile skip onboarding and get "Welcome back" message
- [ ] New users still go through onboarding as before
- [ ] Profile is preloaded into session during registration (avoids redundant DB call on first message)
- [ ] All unit tests pass
- [ ] Ruff lint passes

---

## COMPLETION CHECKLIST

- [ ] `bot/gateway.py` updated with profile check
- [ ] New test: `test_existing_user_without_profile_starts_onboarding`
- [ ] Updated test: `test_existing_user_with_profile_skips_onboarding`
- [ ] `uv run ruff check bot/gateway.py tests/unit/test_onboarding.py` passes
- [ ] `uv run pytest tests/unit/test_onboarding.py -v` passes
- [ ] `uv run pytest tests/unit/ -v` passes

---

## NOTES

- This is a minimal fix. The `_load_user_profile` call adds one DB query during registration for returning users. This is acceptable because registration happens once per session (every 30 minutes at most).
- The existing `_handle_authenticated_message` profile loading (line 289) becomes a no-op for users who registered with this fix, since `user_profile` is already populated in the session. This is a minor performance win.
- After deploying this fix, the prod user (chat_id 275939731) will need to re-authenticate (send passphrase) to trigger the new onboarding flow.
