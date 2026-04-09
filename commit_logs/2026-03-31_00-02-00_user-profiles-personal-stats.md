# User Profiles & Personal Stats Logging

**Date**: 2026-03-31
**Branch**: Menu-and-Personal-Details
**Commit**: 3fd4335

## Changes Implemented

### Database
- `UserProfile` model (name, height_cm, age, gender) with unique user_id constraint
- `PersonalStatsLog` model (weight_kg, body_fat_pct, recorded_at) for time-series measurements
- Supabase migration applied with RLS policies and indexes

### Services
- `user_profile_service.py` — bot-only CRUD (create_user_profile, get_user_profile)
- `personal_stats_service.py` — dual-layer with @tool wrappers (log_personal_stat, get_personal_stat_history)

### Graph
- `LOG_PERSONAL_STATS` action added to ActionType enum and GraphAction literal
- `personal_stats_node` — async node with LLM structured output extraction (PersonalStatExtraction schema)
- `personal_stats_extractor.md` prompt — supports English and Hebrew
- Graph wiring: input_parser → personal_stats → response
- `NODE_CONFIGS` updated with personal_stats_node entry

### Bot
- Deterministic onboarding flow: name → height → age → gender (with validation)
- Profile injection into graph config via `_call_langgraph(user_profile=...)`
- Profile cached on session to avoid repeat DB queries
- `DEFAULT_DEV_PROFILE` fallback for dev/Studio mode

### Tests
- 3 unit tests for personal_stats_node (weight, body fat, accumulation)
- 7 unit tests for onboarding flow (start, validation, completion, skip)
- 7 integration tests for personal stats service (CRUD, history, user isolation)
- 2 E2E graph-api tests (weight logging, body fat logging)
- Updated existing gateway tests for new session fields

## Next Steps
- Update eval datasets with LOG_PERSONAL_STATS examples (English + Hebrew)
- Test onboarding via Telegram bot
- Plan Step 2: user fitness/diet plan storage (LangGraph Store or system prompt injection)
