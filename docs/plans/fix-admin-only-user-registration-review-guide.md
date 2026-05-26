# PR Reading Guide — Admin-only Telegram user registration

A 3-file fix. Read in this order; each file predicts the next.

## 1. Why (start here, no code)
- `commit_logs/2026-05-26_14-27-49_fix-admin-only-user-registration.md` — the bug (poisoned `Authorization` on a shared singleton client), confirmed from prod logs, and why a key swap alone won't fix it.
- `docs/plans/fix-admin-only-user-registration.md` — the full plan, with the verified gotrue 2.28.0 admin-API signatures.

## 2. The keystone change
- `bot/supabase_admin.py` → **`get_or_create_user`**. This is the whole fix. Confirm it no longer calls `sign_in_with_password` anywhere, and now: `_find_user_by_email` → return `is_new=False`, else `admin.create_user` → `is_new=True`. Return shape is `{"user_id", "is_new"}` only.

## 3. The new helper it depends on
- `bot/supabase_admin.py` → **`_find_user_by_email`**. Paginates `admin.list_users(page, per_page=200)`, case-insensitive email match. Admin-only — never mutates the client's `Authorization`.

## 4. The deletions (confirm nothing else used them)
- Removed `refresh_session` and the `access_token`/`refresh_token` return keys. Verify the sole caller `bot/gateway.py:421-432` reads only `result["user_id"]` and `result.get("is_new")` — so dropping the tokens is safe.
- Removed the now-unused `from supabase_auth.errors import AuthApiError`.

## 5. Tests (regression guards)
- `tests/unit/test_supabase_admin.py` → new `TestGetOrCreateUser`: existing-found (no create), new-created (correct attrs, `response.user.id`), pagination (match on page 2), and a guard asserting `sign_in_with_password` is never called.

## Things worth flagging while reviewing
- **`list_users` is O(all users) per registration.** Fine at POC scale; flagged for a future direct-`auth.users`-by-email lookup. Not addressed here.
- **`per_page = 200` is hardcoded.** The pagination test relies on it (returns a 200-item page 1). Reasonable, but a magic number.
- **Singleton client kept, not replaced.** It was never the problem on its own — only `sign_in_with_password` mutating its header was. Kept for efficiency; safe now.
- **`_server_password` retained** even though we no longer sign in. It still sets a deterministic password at create time so per-user auth stays *possible* later (on a separate client). Could be argued as dead weight today.
- **Data-isolation claim:** removing per-user JWTs does not weaken isolation (app-layer `user_id` scoping does the work). Worth confirming you agree with that reading — see `docs/adr/0001`.
- **Duplicate-create race** (two messages, same new user) is not guarded; the plan notes an optional `try/except AuthApiError → re-lookup`. Judged unnecessary for a serial single bot.

## Skip-able
- `docs/plans/fix-admin-only-user-registration.md` is long; the commit log summarizes it. Skim the plan only if you want the task-by-task reasoning.
