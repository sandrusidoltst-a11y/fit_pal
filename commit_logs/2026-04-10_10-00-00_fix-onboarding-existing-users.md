# Fix Onboarding for Existing Users Without Profiles

**Date**: 2026-04-10
**Tag**: fix

## Changes

### Problem
Existing Supabase auth users created before the onboarding feature had no `user_profiles` row. The bot only triggered onboarding when `is_new=True` (new auth user), so these users were shown hardcoded defaults ("Dev User", age 25) instead of being prompted to set up their profile.

### Solution
After `get_or_create_user`, the bot now checks if the user has a profile via `_load_user_profile`. If no profile exists, onboarding triggers regardless of `is_new`.

### Files Modified
- `bot/gateway.py` — Added profile existence check during registration; `needs_onboarding = is_new or existing_profile is None`; preload profile into session
- `tests/unit/test_onboarding.py` — Added `test_existing_user_without_profile_starts_onboarding`; updated existing test to explicitly mock profile
- `tests/unit/test_gateway.py` — Added `_load_user_profile` mock to passphrase registration test

### Files Added
- `.agent/plans/fix-onboarding-for-existing-users-without-profile.md` — Implementation plan

## Next Steps
- Deploy to Railway (merge to main triggers CD)
- Re-authenticate on Telegram (send passphrase) to trigger onboarding for prod user
- Debug personal data display issues if they persist after onboarding
