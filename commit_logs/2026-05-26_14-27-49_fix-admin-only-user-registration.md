# fix: admin-only Telegram user registration (stop poisoned JWT on admin client)

**Date**: 2026-05-26
**Branch**: fix/admin-only-user-registration (off main)
**Plan**: `docs/plans/fix-admin-only-user-registration.md`
**Reading guide**: `docs/plans/fix-admin-only-user-registration-review-guide.md`

## Problem

New Telegram users entering the **correct** passphrase were told "enter the correct code" and could not register. Prod logs (2026-05-26, chat_id `7521587406` — Ori) showed `POST /auth/v1/admin/users` → `403 ... token is expired`, with the `Authorization` header carrying an expired **user JWT** (`eyJ…`) instead of the `sb_secret_…` service key.

Root cause: `get_or_create_user` used one module-level singleton Supabase client for two jobs:
1. `sign_in_with_password` (existence check) — on success, gotrue **overwrites the client's `Authorization` header** with the signed-in user's ~1h JWT.
2. `admin.create_user` (new users) — requires the service key in `Authorization`.

After any existing-user login, the singleton holds a user JWT; once it expires, every **new-user** `create_user` 403s. Selective + intermittent: existing users always pass step 1 and never reach the admin call.

Distinct from the 2026-04-23 incident (revoked legacy key, `403 not_admin`) documented in `brain/planning/friend-signin-bug-resolved-stale-service-role-jwt.md` — that key swap is what *exposed* this one (existing-user logins started succeeding, poisoning the client).

## Change

Rewrote registration to be **admin-API only**:
- Added `_find_user_by_email(client, email)` — paginates `admin.list_users` (per_page 200), case-insensitive match, returns `User | None`. Never signs in.
- `get_or_create_user` → find by synthetic email → return `{"user_id", "is_new": False}` if found, else `admin.create_user` → `{"user_id", "is_new": True}`.
- Removed `sign_in_with_password` (the only thing that mutated `Authorization`), the unused `access_token`/`refresh_token` return keys, the unused `refresh_session` helper, and the now-unused `AuthApiError` import.

Singleton client kept (safe now that nothing mutates its header). `_server_password` kept (still sets a deterministic password at create time; future sign-in remains possible on a separate client).

## Why this is safe for data isolation

Per-user isolation is enforced at the **application layer** — every service query filters by `user_id` (e.g. `src/services/daily_log_service.py:99-100`) — not by the per-user JWTs that were removed. Those tokens were minted and discarded: `bot/gateway.py` reads only `result["user_id"]`. Decision recorded in `docs/adr/0001-app-layer-user-authorization.md` and `PRD.md:394-410`.

## Files

- `bot/supabase_admin.py` — admin-only `get_or_create_user`, new `_find_user_by_email`, removed `refresh_session` + `AuthApiError` import.
- `tests/unit/test_supabase_admin.py` — new `TestGetOrCreateUser` (found / created / pagination / no-sign-in) + `_make_client()` helper.
- `docs/plans/fix-admin-only-user-registration.md` — implementation plan.

## Validation

- `uv run ruff check bot/ tests/unit/test_supabase_admin.py` → clean
- `uv run pytest tests/unit/test_supabase_admin.py -v` → 7 passed
- `uv run pytest tests/unit/` → 200 passed

## Next steps

- Push branch, open PR against `main`.
- Deploy / restart `fitpal-bot`; manual check: new user (Ori) registers (logs show `Created new user`, no 403); existing user still works.
- Scalability follow-up (out of scope): `list_users` lookup is O(users); switch to a direct `auth.users` email query over asyncpg or a `chat_id → user_id` map if the user base grows.
- Consider a short RCA in `docs/rca/` superseding the "no code fix needed" conclusion of the 2026-04 note.
