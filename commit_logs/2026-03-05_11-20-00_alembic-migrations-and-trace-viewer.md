# Alembic Migrations Setup & LangSmith Trace Viewer

**Date**: 2026-03-05
**Commit**: `88ce2d7`
**Branch**: `HITL_and_off_menu`

## Changes Implemented

### Alembic Database Migrations
- Installed Alembic as dev dependency (`alembic==1.18.4`)
- Created `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`
- `env.py` uses `SYNC_DATABASE_URL` from `src.database` (no hardcoded URLs)
- `render_as_batch=True` for SQLite ALTER TABLE support
- `process_revision_directives` strips false-positive nullable ops (SQLite quirk)
- Baseline migration (`cfec3ad93406`) fixes `daily_logs.food_id` NOT NULL → nullable
- ETL script updated: `DELETE FROM` instead of `drop_all`/`create_all`

### LangSmith Trace Viewer
- `scripts/print_trace.py` — prints full conversation flow by thread ID
- Supports `--compact` (no node detail) and `--raw` (JSON dump) modes
- Uses correct LangSmith filter syntax for thread metadata

### Documentation
- CLAUDE.md: Added Alembic to tech stack, project structure, architecture patterns, validation commands
- PRD.md: Marked "Database Migrations (Alembic)" as completed

## Key Discovery
The `daily_logs.food_id` column DDL was `NOT NULL` despite the SQLAlchemy model declaring `nullable=True`. The table was created before the model was updated, and `create_all()` doesn't alter existing tables. The Alembic baseline migration corrected this — estimated/off-menu items can now be inserted with `food_id=None`.

## Next Steps
1. **Off-menu refactor**: Add `source` column to `FoodItem`, insert estimated foods as real rows
2. **User ID**: Add `user_id` to `DailyLog` and `FoodItem` for multi-user support
