# feat: Coach Dashboard Phase 1 (Foundation) — data model + backend scaffold

**Date**: 2026-06-08
**Branch**: claude/practical-meitner-5IOrs
**Plan**: `docs/plans/dashboard-phase-1-foundation.md`

## Scope

Phase 1 of the Coach Dashboard (DASHBOARD_PRD.md §9). Nothing user-visible —
this lays the data model, services, and backend skeleton later phases build on.
Built for a **single coach (Dolev), no coach auth yet** (user directive).

## Decisions (re-opened PRD defaults; flagged for confirmation)

- **D1 — No coach auth in Phase 1.** `get_current_coach_id()` returns the
  existing `DEFAULT_COACH_ID`; it is the single seam where Supabase-JWT auth
  plugs in later. The dashboard app must not be deployed publicly until then.
- **D2 — `coach_id` column on `user_profiles`** (not a join table); backfilled
  to the V1 coach.
- **D3 — Standalone `src/dashboard/` FastAPI app**, separate from
  `src/security/webapp.py` (whose `InternalTokenMiddleware` would 401 a browser).
- **D4 — `macro_targets` row-per-(trainee, day_type)** with
  `day_type ∈ {training, rest}`.

## Change

**Schema (migration — NOT yet applied; see below):**
`supabase/migrations/dashboard_phase1_foundation.sql` — adds
`user_profiles.coach_id` (indexed, Postgres FK to `auth.users`, backfilled),
`personal_stats_log.photo_url`, and a new `macro_targets` table (FK + unique
`(user_id, day_type)` + RLS, defense-in-depth per ADR-0001).

**Models:** `coach_id` on `UserProfile`, `photo_url` on `PersonalStatsLog`, new
`MacroTarget` model.

**Services (plain async, not `@tool` — mirror `user_profile_service`):**
- `src/services/macro_targets_service.py` — `set_macro_targets` (upsert per
  day_type), `get_macro_targets` (both day types).
- `src/services/coach_service.py` — `list_trainees_for_coach`.
- `src/services/personal_stats_service.py` — `create_stat_entry` /
  `_serialize_stat` carry `photo_url` (tool wrappers untouched).

**Dashboard skeleton (`src/dashboard/`):** standalone FastAPI `app` (`/health`
+ `GET /api/dashboard/trainees`), `dependencies.py`
(`get_current_coach_id` stub + `get_db_session`), `routes/trainees.py`.

## Files

- `src/models.py`, `src/services/{macro_targets_service,coach_service}.py`,
  `src/services/personal_stats_service.py`
- `src/dashboard/{__init__,app,dependencies}.py`,
  `src/dashboard/routes/{__init__,trainees}.py`
- `supabase/migrations/dashboard_phase1_foundation.sql`
- `tests/unit/test_dashboard_skeleton.py` (4 tests),
  `tests/integration/test_macro_targets_service.py`,
  `tests/integration/test_coach_service.py`,
  `tests/integration/test_personal_stats_service.py` (+photo_url test)
- `docs/plans/dashboard-phase-1-foundation.md`

## Validation

- `uv run ruff check src/ tests/` → clean
- `uv run pytest tests/unit/` → 204 passed (incl. 4 new dashboard tests)
- New integration tests collect cleanly (15 collected); **not run** — this
  session's container has no Supabase credentials.

## Next steps (require Supabase DB access — could not run here)

1. **Apply the migration** via Supabase MCP (`apply_migration`,
   name `dashboard_phase1_foundation`) or `supabase db push`. Run the
   pre-flight coach-exists check first (in the SQL header / plan Task 1).
2. Run integration tests: `uv run pytest tests/integration/test_macro_targets_service.py
   tests/integration/test_coach_service.py tests/integration/test_personal_stats_service.py -v`.
3. Confirm decisions D1–D4 with Dolev; write a dashboard-auth ADR when D1 is
   revisited (ADR-0001 "second backend service" trigger).
