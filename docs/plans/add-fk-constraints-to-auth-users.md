# Feature: Add Foreign Key Constraints to auth.users

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Add foreign key constraints from all user-scoped public tables (`user_profiles`, `personal_stats_log`, `daily_logs`, `food_items`) to `auth.users(id)`. This enforces referential integrity at the database level — guaranteeing every `user_id` in our tables corresponds to a real Supabase Auth user. Also adds missing RLS policies on `personal_stats_log` (UPDATE/DELETE).

## User Story

As a developer maintaining FitPal
I want database-level FK constraints between my app tables and auth.users
So that orphaned user data cannot exist and user deletion cascades cleanly

## Problem Statement

Currently, `user_id` columns in all four public tables reference `auth.users(id)` by convention only — application code passes the right UUID, but nothing at the database level prevents inserting a fake/orphaned `user_id`. If a user is deleted from Supabase Auth, their data remains orphaned forever. Additionally, `personal_stats_log` is missing UPDATE and DELETE RLS policies.

## Solution Statement

1. Create 2 permanent tagged auth users (dev + e2e_test) as a one-time setup — they stay forever and are identifiable via `user_metadata.source`
2. Reassign orphaned data (dev user_id `00000000-0000-0000-0000-000000000001` in `daily_logs` and `food_items`) to the new dev auth user, then delete remaining orphans
3. Apply a Supabase migration adding FK constraints with appropriate ON DELETE behavior
4. Add missing RLS policies on `personal_stats_log`
5. Update `DEFAULT_DEV_USER_ID` in `src/config.py` and `DEV_USER_CONFIG` in E2E tests to use the real auth user UUIDs
6. No E2E test data cleanup — test data stays in DB, identifiable by tagged test user. E2E tests are smoke tests (verify no blocking errors), not evals.

## Feature Metadata

**Feature Type**: Enhancement
**Estimated Complexity**: Medium
**Primary Systems Affected**: Database schema (Supabase migrations), test fixtures
**Dependencies**: Supabase MCP (`apply_migration`), existing migration history

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

- `src/models.py` (lines 13-100) — All 4 SQLAlchemy models with user_id columns. Note: `FoodItem.user_id` is nullable (shared DB foods have no user), all others are NOT NULL.
- `src/config.py` (lines 22, 31-55) — `DEFAULT_DEV_USER_ID = "00000000-0000-0000-0000-000000000001"` and `get_user_id()` priority chain.
- `bot/supabase_admin.py` (lines 60-104) — `get_or_create_user()` creates real auth.users entries. Returns `response.user.id` (UUID from auth.users).
- `tests/conftest.py` (lines 23-100) — `TEST_USER_A/B` synthetic UUIDs, `async_test_db_session` fixture with transaction rollback isolation. Rollback means test INSERTs never hit the real DB, so FK constraints on the real DB won't affect integration tests.
- `tests/graph_api/test_graph_flows.py` (line 27) — `DEV_USER_CONFIG` uses `DEFAULT_DEV_USER_ID`. E2E tests hit real DB through real server — these WILL be affected.

### Existing Migrations (for reference)

| Version | Name | What it does |
|---------|------|-------------|
| `20260309111629` | `create_food_items_and_daily_logs` | Initial tables |
| `20260309140204` | `add_user_id_columns` | Added user_id to food_items + daily_logs |
| `20260313091244` | `enable_rls_and_create_policies` | RLS + policies for food_items + daily_logs |
| `20260330205432` | `add_user_profiles_and_personal_stats` | New tables + RLS + policies |

### Current State of Data in Production

| Table | Orphaned user_ids (not in auth.users) |
|-------|--------------------------------------|
| `daily_logs` | `00000000-0000-0000-0000-000000000001` (dev default) |
| `food_items` | `00000000-0000-0000-0000-000000000001` (dev default) |
| `user_profiles` | Empty table — no conflicts |
| `personal_stats_log` | Empty table — no conflicts |
| `auth.users` | Only `71a8c873-c6bd-498e-a6ca-bd27d6118329` exists |

### Relevant Documentation

- [Supabase: Managing User Data](https://supabase.com/docs/guides/auth/managing-user-data)
  - Section: "Creating user tables" — canonical FK pattern with ON DELETE CASCADE
  - Why: Official pattern for `REFERENCES auth.users(id) ON DELETE CASCADE`
- [Supabase: Auth Troubleshooting](https://supabase.com/docs/guides/auth/debugging)
  - Section: Foreign key constraint errors
  - Why: Gotchas with ON DELETE RESTRICT blocking user deletion

### Patterns to Follow

**Migration pattern**: Single SQL block via `mcp__supabase__apply_migration`. All previous migrations follow this pattern.

**FK constraint naming convention**: `{table_name}_{column_name}_fkey` (e.g., `user_profiles_user_id_fkey`). This is Postgres default naming.

**ON DELETE behavior per table**:
- `user_profiles` → `ON DELETE CASCADE` (profile should be deleted with user)
- `personal_stats_log` → `ON DELETE CASCADE` (stats should be deleted with user)
- `daily_logs` → `ON DELETE CASCADE` (logs should be deleted with user)
- `food_items` → `ON DELETE SET NULL` (shared DB foods have `user_id=NULL`; estimated foods lose their owner but the food data remains useful for other users who may have logged it)

---

## IMPLEMENTATION PLAN

### Phase 1: Create Permanent Tagged Auth Users

Create 2 permanent auth users in Supabase as a one-time setup. These users stay forever and are identifiable via `user_metadata.source`. They satisfy FK constraints for dev/test workflows.

| User | Email | `user_metadata` | Purpose |
|------|-------|-----------------|---------|
| Dev/Studio | `dev@dev.fitpal.bot` | `{"source": "dev"}` | LangGraph Studio, local dev, `DEFAULT_DEV_USER_ID` fallback |
| E2E Test | `e2e@test.fitpal.bot` | `{"source": "e2e_test"}` | Graph API smoke tests |

After creation, note their Supabase-assigned UUIDs — these replace the old hardcoded values.

### Phase 2: Handle Orphaned Data

Before adding FK constraints, all `user_id` values must exist in `auth.users`. The old dev UUID `00000000-0000-0000-0000-000000000001` has data in `daily_logs` and `food_items`.

**Decision**: Reassign orphaned rows to the new dev auth user UUID (from Phase 1), so historical dev data is preserved under a real auth user. If reassignment is not desired, delete instead.

**IMPORTANT**: Get explicit user permission before running any UPDATE/DELETE on production data. Show the exact SQL and affected row counts first.

### Phase 3: Apply Migration

Single Supabase migration that:
1. Adds FK constraints on all 4 tables
2. Adds missing UPDATE/DELETE RLS policies on `personal_stats_log`

### Phase 4: Update Code References

1. Update `DEFAULT_DEV_USER_ID` in `src/config.py` to the new dev auth user UUID
2. Update `DEV_USER_CONFIG` in `tests/graph_api/test_graph_flows.py` to the new E2E test auth user UUID
3. SQLAlchemy models stay unchanged — FK lives only in Postgres via migration (avoids `Base.metadata.create_all()` issues with `auth.users` not being in our metadata)

### Phase 5: Validation

Run all test tiers to confirm nothing breaks. E2E test data stays in DB after runs — no cleanup needed. Tests are smoke tests that verify no blocking errors, not evals that check output quality.

### No E2E Data Cleanup — Rationale

- E2E tests are **smoke tests** (assert graph completes, not output quality) — data is a side effect, not an artifact under evaluation
- Test data is small (a few rows per run) and identifiable by the tagged E2E test user
- Keeping data allows post-run inspection for debugging if a test starts failing
- If accumulation becomes a problem, a one-time cleanup filtering by E2E user_id is trivial

---

## STEP-BY-STEP TASKS

### Task 1: CREATE permanent tagged auth users (one-time setup)

Use `mcp__supabase__execute_sql` or Supabase admin API to create 2 permanent auth users.

```sql
-- Check: these emails must not already exist
SELECT id, email FROM auth.users
WHERE email IN ('dev@dev.fitpal.bot', 'e2e@test.fitpal.bot');
```

Create via Supabase admin API (not raw SQL — auth.users is managed by Supabase Auth):
```python
# Dev user
await client.auth.admin.create_user({
    "email": "dev@dev.fitpal.bot",
    "password": "<generate-secure-password>",
    "email_confirm": True,
    "user_metadata": {"source": "dev", "description": "LangGraph Studio and local development"},
})

# E2E test user
await client.auth.admin.create_user({
    "email": "e2e@test.fitpal.bot",
    "password": "<generate-secure-password>",
    "email_confirm": True,
    "user_metadata": {"source": "e2e_test", "description": "Graph API smoke tests"},
})
```

Record the returned UUIDs — they'll be used in Tasks 2, 3, and 4.

- **VALIDATE**: `SELECT id, email, raw_user_meta_data->>'source' AS source FROM auth.users;` — should show 3 users (1 real + 2 tagged)

### Task 2: HANDLE orphaned data in production

**IMPORTANT**: Show the exact SQL and row counts to the user and get explicit permission before executing.

```sql
-- READ ONLY: Check what's orphaned
SELECT 'daily_logs' AS table_name, COUNT(*) AS orphan_count
FROM daily_logs
WHERE user_id NOT IN (SELECT id FROM auth.users)
UNION ALL
SELECT 'food_items', COUNT(*)
FROM food_items
WHERE user_id IS NOT NULL AND user_id NOT IN (SELECT id FROM auth.users);
```

Then, after user approval — reassign orphaned rows to the new dev auth user:
```sql
-- Reassign dev data to the new dev auth user
UPDATE daily_logs
SET user_id = '<new-dev-user-uuid>'
WHERE user_id = '00000000-0000-0000-0000-000000000001';

UPDATE food_items
SET user_id = '<new-dev-user-uuid>'
WHERE user_id = '00000000-0000-0000-0000-000000000001';
```

- **VALIDATE**: Re-run the orphan count query — should return 0 for all tables.

### Task 3: APPLY Supabase migration — FK constraints + missing RLS policies

Use `mcp__supabase__apply_migration` with name `add_fk_constraints_and_rls_updates`.

```sql
-- FK constraints
ALTER TABLE public.user_profiles
  ADD CONSTRAINT user_profiles_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE public.personal_stats_log
  ADD CONSTRAINT personal_stats_log_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE public.daily_logs
  ADD CONSTRAINT daily_logs_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE public.food_items
  ADD CONSTRAINT food_items_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE SET NULL;

-- Missing RLS policies on personal_stats_log
CREATE POLICY "Users can update own stats" ON public.personal_stats_log
  FOR UPDATE
  USING ((SELECT auth.uid()) = user_id)
  WITH CHECK ((SELECT auth.uid()) = user_id);

CREATE POLICY "Users can delete own stats" ON public.personal_stats_log
  FOR DELETE
  USING ((SELECT auth.uid()) = user_id);
```

- **VALIDATE**: Run via Supabase MCP:
  ```sql
  SELECT tc.table_name, tc.constraint_name, ccu.table_schema, ccu.table_name AS foreign_table
  FROM information_schema.table_constraints tc
  JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
  WHERE tc.constraint_type = 'FOREIGN KEY'
    AND tc.table_name IN ('user_profiles', 'personal_stats_log', 'daily_logs', 'food_items');
  ```

### Task 4: UPDATE code references to use real auth user UUIDs

**UPDATE** `src/config.py` (line 22):
- Change `DEFAULT_DEV_USER_ID` from `"00000000-0000-0000-0000-000000000001"` to the new dev auth user UUID (from Task 1)

**UPDATE** `tests/graph_api/test_graph_flows.py` (line 27):
- Change `DEV_USER_CONFIG` user_id from `"00000000-0000-0000-0000-000000000001"` to the new E2E test auth user UUID (from Task 1)

- **GOTCHA**: `DEFAULT_DEV_USER_ID` is also referenced in unit tests (`test_auth_handler.py`) for testing the fallback behavior. Those tests mock the config and assert the fallback value — update the expected value there too.
- **VALIDATE**: `uv run ruff check .` — no syntax errors

### Task 5: RUN unit tests

Unit tests are fully mocked — no DB interaction. Should pass with the updated `DEFAULT_DEV_USER_ID` value.

- **VALIDATE**: `uv run pytest tests/unit/ -v`

### Task 6: RUN integration tests (should pass unchanged)

Integration tests use `async_test_db_session` with transaction rollback. Since the rollback happens before any data hits the real DB, FK constraints on the real DB don't affect them. The synthetic `TEST_USER_A/B` UUIDs live only within the rolled-back transaction.

- **VALIDATE**: `uv run pytest tests/integration/ -v`

### Task 7: RUN E2E tests

E2E tests now use the permanent E2E test auth user. Data written during tests stays in DB — no cleanup needed.

- **VALIDATE**: `uv run pytest tests/graph_api/ -v -s`

---

## TESTING STRATEGY

### Unit Tests
No changes needed — fully mocked, no DB interaction.

### Integration Tests
No changes needed — transaction rollback isolation means FK constraints on the real DB are never hit. The `async_test_db_session` fixture creates a savepoint, and all test data lives within that savepoint which is rolled back at the end.

**Key insight**: `Base.metadata.create_all()` is NOT used in integration tests (tables already exist in Supabase). The fixture just opens a connection to the existing tables. Since we're NOT adding FK to SQLAlchemy models (Option A), there's no model-level change to affect tests.

### E2E / Graph API Tests
Updated to use permanent E2E test auth user UUID. No teardown cleanup — test data stays in DB, identifiable by the tagged test user (`e2e@test.fitpal.bot`, `user_metadata.source = "e2e_test"`). E2E tests are smoke tests that verify graph completion, not output quality.

### Edge Cases
- Verify that deleting a user from Supabase Auth cascades to all 4 tables
- Verify that `food_items` with `user_id=NULL` (shared DB foods) are unaffected
- Verify that inserting with a non-existent user_id fails (FK enforcement works)
- Verify that LangGraph Studio works with the new `DEFAULT_DEV_USER_ID` (real dev auth user)

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style
```bash
uv run ruff check .
```

### Level 2: Unit Tests
```bash
uv run pytest tests/unit/ -v
```

### Level 3: Integration Tests
```bash
uv run pytest tests/integration/ -v
```

### Level 4: E2E Tests
```bash
uv run pytest tests/graph_api/ -v -s
```

### Level 5: DB Validation (via Supabase MCP)
```sql
-- Verify FK constraints exist
SELECT tc.table_name, tc.constraint_name
FROM information_schema.table_constraints tc
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_name IN ('user_profiles', 'personal_stats_log', 'daily_logs', 'food_items');

-- Verify RLS policies on personal_stats_log
SELECT policyname, cmd FROM pg_policies
WHERE tablename = 'personal_stats_log';

-- Verify no orphaned user_ids remain
SELECT 'daily_logs' AS t, COUNT(*) FROM daily_logs WHERE user_id NOT IN (SELECT id FROM auth.users)
UNION ALL
SELECT 'food_items', COUNT(*) FROM food_items WHERE user_id IS NOT NULL AND user_id NOT IN (SELECT id FROM auth.users);
```

---

## ACCEPTANCE CRITERIA

- [ ] 2 permanent tagged auth users created (dev + e2e_test) with `user_metadata.source`
- [ ] Orphaned dev data reassigned to new dev auth user (user approval obtained first)
- [ ] FK constraints exist on all 4 tables referencing `auth.users(id)`
- [ ] `user_profiles`, `personal_stats_log`, `daily_logs` use ON DELETE CASCADE
- [ ] `food_items` uses ON DELETE SET NULL (preserves shared food data)
- [ ] Missing UPDATE/DELETE RLS policies added to `personal_stats_log`
- [ ] `DEFAULT_DEV_USER_ID` in `src/config.py` points to real dev auth user UUID
- [ ] `DEV_USER_CONFIG` in E2E tests points to real E2E test auth user UUID
- [ ] All unit tests pass
- [ ] All integration tests pass (rollback isolation — unaffected)
- [ ] All E2E tests pass (using permanent E2E test auth user, no cleanup)
- [ ] SQLAlchemy models NOT modified (FK is DB-only via migration)
- [ ] LangGraph Studio works with new dev user UUID

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order (Tasks 1-7)
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit + integration + E2E)
- [ ] No linting errors
- [ ] User approved all DB write operations (UPDATE/DELETE)
- [ ] Acceptance criteria all met

---

## NOTES

### Design Decisions

1. **Permanent tagged auth users (not dynamic create/delete)**: Instead of creating and deleting test auth users per test run, we create 2 permanent users tagged with `user_metadata.source`. This lets us keep E2E test data in the DB for debugging, avoids test flakiness from network calls during setup/teardown, and provides clear identification of dev vs test vs real users.

2. **SQLAlchemy models unchanged**: The FK constraint lives only in Postgres via Supabase migration. Adding `ForeignKey("auth.users.id")` to SQLAlchemy models would cause `Base.metadata.create_all()` issues since `auth.users` is Supabase-managed and not in our metadata. This is the cleanest approach.

3. **ON DELETE SET NULL for food_items**: Unlike other tables, `food_items` has shared database foods (`user_id=NULL`) and estimated foods (`user_id=<uuid>`). If a user is deleted, their estimated foods should lose ownership (SET NULL) rather than being deleted, because other users may have daily_log entries referencing those food items via `food_id` FK.

4. **No E2E test data cleanup**: E2E tests are smoke tests — they verify the graph completes without blocking errors, not output quality. Test data is small, identifiable by tagged user, and useful for post-run debugging. If accumulation ever becomes a problem, a simple `DELETE WHERE user_id = '<e2e-user-uuid>'` handles it.

5. **Integration tests unaffected**: The transaction rollback isolation in `async_test_db_session` means test INSERTs with synthetic user_ids never reach the real DB where FK constraints live. The savepoint/rollback happens at a lower level than constraint checking on committed data.

6. **Reassign orphaned data, not delete**: The old dev data (`00000000-...`) in `daily_logs` and `food_items` gets reassigned to the new dev auth user rather than deleted, preserving historical dev data under a properly FK'd user.

### Auth User Identification Strategy

| Email pattern | `user_metadata.source` | Purpose |
|---------------|----------------------|---------|
| `*@telegram.fitpal.bot` | *(none)* | Real Telegram users |
| `dev@dev.fitpal.bot` | `"dev"` | LangGraph Studio / local dev |
| `e2e@test.fitpal.bot` | `"e2e_test"` | Graph API smoke tests |

Query to find all non-real users:
```sql
SELECT id, email, raw_user_meta_data->>'source' AS source
FROM auth.users
WHERE raw_user_meta_data->>'source' IS NOT NULL;
```

### Risks

- **Cascade deletion scope**: ON DELETE CASCADE on `daily_logs` means deleting a user wipes all their nutrition history. This is correct behavior but irreversible.
- **food_items SET NULL orphans**: After user deletion, estimated food items with `user_id=NULL` become indistinguishable from shared DB foods (except by `source="estimated"`). This is acceptable since the food data itself is still useful.
- **DEFAULT_DEV_USER_ID change**: Any existing local dev setups or Studio sessions using the old UUID will get a new user context. This is a one-time disruption.

### Confidence Score: 9/10

High confidence because:
- Permanent auth users are simpler than dynamic create/delete
- Integration tests are isolated by rollback (no FK impact)
- Unit tests are fully mocked (no impact)
- E2E test changes are minimal (just swap a UUID string)
- Migration SQL is straightforward
- No complex teardown logic needed

Risk factors:
- Must get user approval for production data reassignment
- Unit tests referencing `DEFAULT_DEV_USER_ID` need updated expected values
