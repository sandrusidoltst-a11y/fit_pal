# feat: add per-user nutrition plan injection into response node

**Date**: 2026-04-13
**Branch**: plan-and-coach-mind
**Commit**: 431483a

## Changes

### DB + Service Layer
- Added `nutrition_plan: Mapped[Optional[str]]` (Text, nullable) to `UserProfile` model
- Added `Text` import to `src/models.py`
- Added `set_nutrition_plan()` async service function to update a user's plan
- Updated `get_user_profile()` to return `nutrition_plan` in the dict
- Applied Supabase migration: `ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS nutrition_plan TEXT`

### Runtime Context
- Added `nutrition_plan: str` to `UserProfile` TypedDict in `src/context.py`
- Added placeholder plan to `DEFAULT_DEV_PROFILE` for Studio dev

### Agent Integration
- Injected current time (`datetime.now().strftime("%A, %Y-%m-%d %H:%M")`) into response_node system message
- Injected nutrition plan section into system message (with "No plan set" fallback)
- Restructured system message: `Current time` -> `_SYSTEM_PROMPT` -> `User Profile` -> `Nutrition Plan` -> `Context JSON`

### Input Parser
- Updated `QUERY_DAILY_STATS` description and examples to cover plan-vs-actual questions

### Bot Gateway
- Updated onboarding completion to preserve existing `nutrition_plan` from DB in session cache

### Coach Tooling
- Created `src/scripts/set_plan.py` CLI script for uploading plan files per user

### Tests
- Added 3 unit tests: time injection, plan injection, no-plan fallback
- Created `tests/integration/test_user_profile_service.py` with 4 tests (get returns None, set works, raises on missing, overwrite works)
- All 99 unit tests + 30 integration tests passing

### Other
- Added `.mcp.json` to `.gitignore`

## Next Steps
- Manual test: run `set_plan.py` for a real user, verify in Studio and Telegram
- Run input parser eval to verify routing changes don't regress
- Future: training day vs non-training day awareness
