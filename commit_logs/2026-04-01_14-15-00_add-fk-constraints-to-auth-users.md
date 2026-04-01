# Add FK Constraints to auth.users

**Date**: 2026-04-01
**Branch**: Menu-and-Personal-Details
**Commit**: a095f18

## Changes Implemented

### Database (Supabase Migration: `add_fk_constraints_and_rls_updates`)
- Added FK constraints on all 4 user-scoped tables → `auth.users(id)`:
  - `user_profiles` → ON DELETE CASCADE
  - `personal_stats_log` → ON DELETE CASCADE
  - `daily_logs` → ON DELETE CASCADE
  - `food_items` → ON DELETE SET NULL (preserves shared food data)
- Added missing RLS policies on `personal_stats_log` (UPDATE + DELETE)
- Created 2 permanent tagged auth users:
  - `dev@dev.fitpal.bot` (`fbeeb45f-d728-4c7c-9e6d-7b9b41685da7`) — LangGraph Studio / local dev
  - `e2e@test.fitpal.bot` (`72c10336-9d61-4357-9851-20cbb4d32b1a`) — Graph API smoke tests
- Reassigned 15 orphaned rows (13 daily_logs + 2 food_items) from old dev UUID to new dev auth user

### Code Changes
- `src/config.py` — `DEFAULT_DEV_USER_ID` updated to real dev auth user UUID
- `tests/conftest.py` — `TEST_USER_A/B` updated to real auth user UUIDs (FK compliance)
- `tests/graph_api/test_graph_flows.py` — `DEV_USER_CONFIG` updated to E2E test auth user UUID
- `PRD.md` — Added backlog items for auth metadata sync and alternative Telegram auth methods

### Deviation from Plan
The plan assumed integration tests wouldn't be affected by FK constraints due to transaction rollback isolation. However, PostgreSQL checks IMMEDIATE FK constraints at INSERT time, not commit time. Fixed by pointing `TEST_USER_A/B` to real auth user UUIDs.

## Validation Results
- `ruff check .` — all passed
- `pytest tests/unit/` — 95/95 passed
- `pytest tests/integration/` — 26/26 passed
- `pytest tests/graph_api/` — 13/13 passed

## Next Steps
- Push branch and create PR to merge into main
- Smoke test bot via Telegram with new dev user
- Consider adding FK enforcement test (insert with fake user_id, expect failure)
