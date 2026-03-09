# Phase 3 Step 1 — Supabase Project Setup

**Date**: 2026-03-09
**Commit**: `9384586`
**Branch**: `main`

## Changes Implemented

### 1. Supabase Project Created
- Project `fitpal` in `eu-central-1` (free tier)
- Project ID: `zpxurpfyebmsynwvsdoc`
- URL: `https://zpxurpfyebmsynwvsdoc.supabase.co`

### 2. Supabase Schema (via MCP migration)
- `food_items` table with UUID PK (`gen_random_uuid()`), `source` column
- `daily_logs` table with UUID PK, FK to `food_items`
- Indexes: `idx_food_items_name`, `idx_daily_logs_timestamp`

### 3. ETL Script Refactored (`src/scripts/ingest_simple_db.py`)
- Extracted `parse_csv()` — pure data parsing shared by both targets
- `ingest_sqlite()` — ORM path (unchanged behavior)
- `ingest_postgres()` — raw SQL path (bypasses ORM integer PK mismatch)
- `argparse` CLI with `--target sqlite|supabase` (defaults to `sqlite`)

### 4. Dependency Added
- `psycopg2-binary>=2.9.11` in `pyproject.toml`

### 5. Environment Variables
- Added `SUPABASE_PROJECT_ID`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_DB_URL` to `.env`

## Verification
- 335 food items seeded to Supabase (UUID IDs, `source='database'`)
- 0 rows in `daily_logs` (expected)
- SQLite regression: ETL works, 71/71 unit tests passing
- Security advisors: RLS disabled (expected, will be added with auth in later step)

## Files Changed
- `pyproject.toml` — added `psycopg2-binary`
- `uv.lock` — lockfile update
- `src/scripts/ingest_simple_db.py` — dual-target refactor

## Not Changed (critical constraint)
- `src/models.py`, `src/database.py`, `src/config.py`
- All nodes, tools, services, schemas, state types

## Next Steps
- Phase 3 Step 2: Add `user_id` column, RLS policies, auth integration
- Phase 3 Step 3: Switch application code from SQLite to Supabase
