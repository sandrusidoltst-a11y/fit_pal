# Feature: Setup Alembic Database Migrations

The following plan should be complete, but validate documentation and codebase patterns before implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files.

## Feature Description

Set up Alembic as the database migration tool for FitPal. This is foundational infrastructure — all future schema changes (adding `source` column to `FoodItem`, adding `user_id` for multi-user) will be managed through versioned migration files. The existing `nutrition.db` with ~8,000 food items must be preserved.

## User Story

As a developer
I want schema changes managed through versioned Alembic migrations
So that I can safely evolve the database without losing existing data

## Problem Statement

Currently, the only way to create/modify the schema is `Base.metadata.drop_all()` + `create_all()` in the ETL script, which destroys all data. There's no way to add a column to an existing table without recreating it.

## Solution Statement

Install Alembic, configure it to use the existing sync SQLAlchemy engine, create a baseline migration that stamps the current schema, and update the ETL script to stop dropping/recreating tables.

## Feature Metadata

**Feature Type**: Infrastructure
**Estimated Complexity**: Low
**Primary Systems Affected**: Database layer, ETL script
**Dependencies**: `alembic` package

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ BEFORE IMPLEMENTING

- `src/config.py` (lines 10-13) — `BASE_DIR`, `DB_PATH`, `DATABASE_URL` definitions
- `src/models.py` (full file) — `Base`, `FoodItem`, `DailyLog` model definitions
- `src/database.py` (full file) — Sync + async engine setup, `SYNC_DATABASE_URL`
- `src/scripts/ingest_simple_db.py` (lines 27-35) — ETL script with `drop_all`/`create_all`
- `pyproject.toml` — Dependencies (alembic not yet present)
- `tests/conftest.py` (lines 44-46) — Test DB uses `Base.metadata.create_all()` on in-memory SQLite (leave as-is)

### New Files to Create

- `alembic.ini` — Alembic config at project root
- `alembic/env.py` — Migration environment (imports Base, models, sync engine)
- `alembic/script.py.mako` — Migration template
- `alembic/versions/<hash>_baseline.py` — Baseline migration stamping current schema

### Patterns to Follow

**Database URL**: Reuse `SYNC_DATABASE_URL` from `src.database` for Alembic (sync engine).

**Import style**: Use absolute imports from `src.*`:
```python
from src.database import SYNC_DATABASE_URL
from src.models import Base
```

**Package manager**: `uv add --dev alembic` (never pip)

---

## IMPLEMENTATION PLAN

### Phase 1: Install & Initialize

Install Alembic as a dev dependency and create the `alembic/` directory structure with proper configuration.

### Phase 2: Configure env.py

Wire Alembic's `env.py` to use FitPal's existing sync database URL and model metadata. This is the critical file — it tells Alembic where the DB is and what the target schema looks like.

### Phase 3: Baseline Migration

Generate the initial migration that represents the current schema. Since the DB already exists with data, this migration uses `--autogenerate` to capture the schema, then we stamp it as applied without running it (the tables already exist).

### Phase 4: Update ETL Script

Remove `drop_all`/`create_all` from the ingest script. Replace with Alembic-aware approach that only recreates `food_items` data without touching schema.

### Phase 5: Validation

Verify migrations work, existing data is preserved, and autogenerate detects no drift.

---

## STEP-BY-STEP TASKS

### Task 1: ADD alembic dependency

- **IMPLEMENT**: `uv add --dev alembic`
- **VALIDATE**: `uv run alembic --version`

### Task 2: CREATE alembic.ini

- **IMPLEMENT**: Create `alembic.ini` at project root with minimal config:
  - `script_location = alembic`
  - `sqlalchemy.url` can be left empty (we override in `env.py`)
  - Set `file_template` to include readable names: `%%(year)d_%%(month).2d_%%(day).2d_%%(rev)s_%%(slug)s`
- **GOTCHA**: Do NOT hardcode the database URL in `alembic.ini` — it comes from `env.py`
- **VALIDATE**: File exists at project root

### Task 3: CREATE alembic/env.py

- **IMPLEMENT**: Custom `env.py` that:
  1. Adds project root to `sys.path` so `from src.*` imports work
  2. Loads `.env` via `dotenv` (consistent with rest of project)
  3. Imports `SYNC_DATABASE_URL` from `src.database`
  4. Imports `Base` from `src.models` (this also imports all models via relationship refs)
  5. Sets `target_metadata = Base.metadata`
  6. Overrides `config.set_main_option("sqlalchemy.url", SYNC_DATABASE_URL)`
  7. Implements standard `run_migrations_offline()` and `run_migrations_online()` using sync engine
- **PATTERN**: Use sync engine only (Alembic is sync-first, and we already have a sync URL)
- **GOTCHA**: `sys.path` insertion must happen before any `src.*` imports
- **GOTCHA**: Must import `src.models` to ensure all models register with `Base.metadata`
- **VALIDATE**: `uv run alembic check` should run without import errors

### Task 4: CREATE alembic/script.py.mako

- **IMPLEMENT**: Standard Alembic migration template (default from `alembic init`)
- **VALIDATE**: File exists

### Task 5: CREATE alembic/versions/ directory

- **IMPLEMENT**: `mkdir alembic/versions`
- **VALIDATE**: Directory exists

### Task 6: GENERATE baseline migration

- **IMPLEMENT**: `uv run alembic revision --autogenerate -m "baseline"`
- This will generate a migration file that creates `food_items` and `daily_logs` tables
- **REVIEW**: Open the generated file and verify it matches the current schema exactly
- **GOTCHA**: The migration's `upgrade()` will have `op.create_table(...)` for both tables. This is correct — it represents the full schema as the starting point.
- **VALIDATE**: Migration file generated in `alembic/versions/`

### Task 7: STAMP baseline as applied

- **IMPLEMENT**: `uv run alembic stamp head`
- This marks the baseline migration as "already applied" in the DB without running it (since tables already exist)
- This creates an `alembic_version` table in `nutrition.db` with the current revision hash
- **VALIDATE**: `uv run alembic current` shows the baseline revision
- **VALIDATE**: `uv run alembic check` reports no pending changes

### Task 8: UPDATE ETL script

**File**: `src/scripts/ingest_simple_db.py`

- **REMOVE**: `Base.metadata.drop_all(bind=engine)` (line 34)
- **REMOVE**: `Base.metadata.create_all(bind=engine)` (line 35)
- **REPLACE WITH**: Delete all rows from `food_items` table (and cascade to `daily_logs` FK) then re-insert from CSV. This preserves the schema while refreshing data.
- **IMPLEMENT**:
  ```python
  # Clear existing food data (preserves schema)
  session.execute(text("DELETE FROM food_items"))
  session.commit()
  ```
- **GOTCHA**: Deleting from `food_items` may fail if `daily_logs` has FK references. Add `PRAGMA foreign_keys=OFF` before delete, or delete `daily_logs` first, or use cascade. Since daily_logs test data doesn't matter, simplest to delete from both tables.
- **IMPORTS**: Add `from sqlalchemy import text`
- **VALIDATE**: `uv run python -m src.scripts.ingest_simple_db` completes without error
- **VALIDATE**: Verify food items count: `uv run python -c "from src.database import get_db_session; s=get_db_session(); print(s.execute(__import__('sqlalchemy').text('SELECT COUNT(*) FROM food_items')).scalar())"`

### Task 9: VERIFY no schema drift

- **IMPLEMENT**: `uv run alembic check`
- **VALIDATE**: Output says "No new upgrade operations detected"
- This confirms that models.py and the DB are in sync

---

## TESTING STRATEGY

### Unit Tests

No new unit tests needed — this is infrastructure setup. Existing tests use in-memory SQLite with `Base.metadata.create_all()` which is fine for test isolation (tests don't need Alembic).

### Integration Tests

- Run `uv run alembic upgrade head` on a fresh DB to verify the baseline migration creates the correct schema
- Run `uv run alembic downgrade base` to verify rollback works
- Run existing test suite to confirm nothing broke

### Edge Cases

- ETL script re-run after migration setup (should work without schema errors)
- `alembic check` after no model changes (should report clean)

---

## VALIDATION COMMANDS

### Level 1: Alembic Setup

```bash
uv run alembic --version
uv run alembic current
uv run alembic check
```

### Level 2: Unit Tests (no regressions)

```bash
uv run pytest tests/unit/ -v
```

### Level 3: ETL Script

```bash
uv run python -m src.scripts.ingest_simple_db
```

### Level 4: Fresh DB Test

```bash
# Backup existing DB, test from scratch
cp data/nutrition.db data/nutrition.db.bak
rm data/nutrition.db
uv run alembic upgrade head
uv run python -m src.scripts.ingest_simple_db
uv run alembic check
# Restore
mv data/nutrition.db.bak data/nutrition.db
```

---

## ACCEPTANCE CRITERIA

- [ ] `uv run alembic current` shows baseline revision
- [ ] `uv run alembic check` reports no schema drift
- [ ] `alembic/env.py` uses `SYNC_DATABASE_URL` from `src.database` (no hardcoded URLs)
- [ ] Existing `nutrition.db` data is untouched (food_items count same as before)
- [ ] ETL script no longer drops/creates tables
- [ ] `uv run pytest tests/unit/ -v` all pass (no regressions)
- [ ] `alembic/versions/` contains one baseline migration file

---

## COMPLETION CHECKLIST

- [ ] Alembic installed as dev dependency
- [ ] `alembic.ini` at project root
- [ ] `alembic/env.py` wired to project DB and models
- [ ] Baseline migration generated and stamped
- [ ] ETL script updated (no more drop_all/create_all)
- [ ] All validation commands pass
- [ ] Existing data preserved

---

## NOTES

- **Tests stay as-is**: Test fixtures use in-memory SQLite with `Base.metadata.create_all()`. This is standard practice — tests don't run migrations, they create fresh schemas per test session.
- **Future migrations**: After this setup, adding the `source` column to `FoodItem` (off-menu feature) is just: update `models.py`, run `uv run alembic revision --autogenerate -m "add source column"`, then `uv run alembic upgrade head`.
- **Alembic as dev dep**: Migrations are a dev/deploy concern, not a runtime dependency. Added to `[dependency-groups] dev`.

**Confidence Score**: 9/10 — straightforward Alembic setup with well-understood codebase.
