# Feature: Phase 3 Step 1 — Supabase Project Setup

The following plan should be complete, but validate documentation and codebase patterns before implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files.

## Context

FitPal currently runs on local SQLite. Phase 3 migrates to Supabase Postgres for multi-user production deployment. Step 1 is the foundation: create the Supabase project, define the Postgres schema (with UUID primary keys), seed the nutrition data, and adapt the ETL script to work against both databases.

**Critical constraint**: Step 1 does NOT change any graph code, tools, services, state types, or node implementations. The application code stays on SQLite with integer PKs. Only the Supabase remote schema and the ETL script are touched.

## User Story

As the FitPal developer
I want a production-ready Supabase Postgres database with my nutrition schema and seeded data
So that I have the foundation for multi-user deployment in subsequent steps

## Feature Metadata

**Feature Type**: New Capability (infrastructure)
**Estimated Complexity**: Medium
**Primary Systems Affected**: Supabase (remote), ETL script, project dependencies
**Dependencies**: Supabase MCP tools, `psycopg2-binary` package

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ BEFORE IMPLEMENTING

- `src/scripts/ingest_simple_db.py` — Current ETL script to refactor (dual-target)
- `src/models.py` — Current SQLAlchemy models (schema reference for Postgres CREATE TABLE)
- `src/database.py` — Current DB engine setup (understand sync/async split)
- `src/config.py` (lines 11-13) — `BASE_DIR`, `DB_PATH`, `DATABASE_URL` definitions
- `.env` — Add new Supabase env vars (file is gitignored)
- `.gitignore` (line 30) — Confirms `.env` is gitignored
- `pyproject.toml` — Add `psycopg2-binary` dependency

### Files NOT Changed (critical constraint)

- `src/models.py` — stays with integer PKs (changed in Step 2/3)
- `src/database.py` — stays with SQLite engines (changed in Step 3)
- `src/config.py` — stays with SQLite DATABASE_URL (changed in Step 3)
- All nodes, tools, services, schemas, state types — untouched

### Patterns to Follow

**ETL script pattern** (from current `ingest_simple_db.py`):
- `clean_val()` handles CSV quirks ('t', 'a', commas, empty)
- Normalize to per-100g: `(value / grams) * 100`, rounded to 2 decimal places
- Category prepend for "Breads" items
- Delete order: `daily_logs` first, then `food_items` (FK constraint)
- Bulk insert via `session.add_all()` for SQLite path

---

## IMPLEMENTATION PLAN

### Phase 1: Supabase Project Creation

Create the Supabase project via MCP tools and retrieve connection details.

### Phase 2: Schema Migration

Apply CREATE TABLE migration to Supabase with UUID PKs via MCP.

### Phase 3: ETL Script Adaptation

Refactor `ingest_simple_db.py` into:
- `parse_csv()` — pure data extraction (shared by both targets)
- `ingest_sqlite()` — existing ORM path (integer PKs)
- `ingest_postgres()` — raw SQL path (UUID PKs, bypasses ORM model)
- `argparse` CLI with `--target sqlite|supabase`

### Phase 4: Data Seeding & Verification

Run ETL against Supabase, verify data, run regression tests on SQLite.

---

## STEP-BY-STEP TASKS

### Task 1: CREATE Supabase Project

1. Call `mcp__supabase__list_organizations` to get the org ID
2. Call `mcp__supabase__get_cost` with `type: "project"`, `organization_id: <org_id>`
3. Call `mcp__supabase__confirm_cost` with the returned amount
4. Call `mcp__supabase__create_project` with:
   - `name`: `fitpal`
   - `region`: `eu-central-1`
   - `organization_id`: from step 1
   - `confirm_cost_id`: from step 3
5. Poll `mcp__supabase__get_project` until status is `ACTIVE_HEALTHY`
6. Call `mcp__supabase__get_project_url` to get the API URL
7. Call `mcp__supabase__get_publishable_keys` to get the anon key

- **VALIDATE**: Project appears in `mcp__supabase__list_projects`

### Task 2: UPDATE `.env` — Add Supabase Connection Variables

Add these variables (do NOT remove existing ones):

```
# Supabase (Phase 3)
SUPABASE_PROJECT_ID=<project_ref>
SUPABASE_URL=<api_url from get_project_url>
SUPABASE_ANON_KEY=<publishable_key>
SUPABASE_DB_URL=postgresql+psycopg2://postgres.<project_ref>:<password>@aws-0-eu-central-1.pooler.supabase.com:5432/postgres
```

**NOTE**: The database password is generated during project creation. The connection string uses the **session pooler** (port 5432). The exact pooler hostname format is `aws-0-<region>.pooler.supabase.com`. Check the Supabase dashboard or project details for the exact connection string if the MCP tool doesn't return it.

- **GOTCHA**: `.env` is gitignored — this is correct, secrets stay local
- **VALIDATE**: `grep SUPABASE .env` shows all 4 variables

### Task 3: APPLY Schema Migration to Supabase

Use `mcp__supabase__apply_migration` with name `create_food_items_and_daily_logs`.

**Exact SQL**:

```sql
CREATE TABLE public.food_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    calories DOUBLE PRECISION,
    protein DOUBLE PRECISION,
    fat DOUBLE PRECISION,
    carbs DOUBLE PRECISION,
    source TEXT NOT NULL DEFAULT 'database'
);

CREATE INDEX idx_food_items_name ON public.food_items (name);

CREATE TABLE public.daily_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    food_id UUID REFERENCES public.food_items(id),
    amount_g DOUBLE PRECISION NOT NULL,
    calories DOUBLE PRECISION NOT NULL,
    protein DOUBLE PRECISION NOT NULL,
    carbs DOUBLE PRECISION NOT NULL,
    fat DOUBLE PRECISION NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    meal_type TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ,
    original_text TEXT
);

CREATE INDEX idx_daily_logs_timestamp ON public.daily_logs (timestamp);
```

**Design notes**:
- `gen_random_uuid()` is built-in to Postgres 13+ (no extension needed)
- `DOUBLE PRECISION` maps to SQLAlchemy `Float`
- `TIMESTAMPTZ` maps to SQLAlchemy `DateTime(timezone=True)`
- `created_at DEFAULT now()` is server-side (current model uses Python-side lambda — Postgres native is better)
- `food_id` is nullable (matches current model) for estimated items

- **VALIDATE**: `mcp__supabase__list_tables` shows both tables with correct columns

### Task 4: ADD `psycopg2-binary` Dependency

```bash
uv add psycopg2-binary
```

- **GOTCHA**: This is a runtime dependency (not dev), needed for ETL script to connect to Postgres
- **VALIDATE**: `grep psycopg2 pyproject.toml` shows the dependency

### Task 5: REFACTOR `src/scripts/ingest_simple_db.py` — Dual-Target ETL

Refactor the script into three functions + argparse CLI:

**Structure**:

```python
import argparse
import csv
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from src.config import BASE_DIR

load_dotenv()

CSV_PATH = os.path.join(BASE_DIR, "data", "nutrients_csvfile.csv")


def clean_val(val):
    """Unchanged — handles CSV quirks ('t', 'a', commas, empty)."""
    if not val:
        return 0.0
    val = val.strip().lower()
    if val in ['t', 'a']:
        return 0.0
    val = val.replace(',', '')
    try:
        return float(val)
    except ValueError:
        return 0.0


def parse_csv() -> list[dict]:
    """Parse CSV and normalize all values to per-100g. Pure data, no DB dependency."""
    items = []
    with open(CSV_PATH, mode='r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            name = row.get("Food")
            grams_str = row.get("Grams")

            if not name or not grams_str:
                continue

            grams = clean_val(grams_str)
            if grams == 0:
                print(f"Skipping {name} due to 0 grams.")
                continue

            calories = clean_val(row.get("Calories"))
            protein = clean_val(row.get("Protein"))
            fat = clean_val(row.get("Fat"))
            carbs = clean_val(row.get("Carbs"))
            category = row.get("Category")

            if category and "Breads" in category:
                name = f"{category} - {name}"

            items.append({
                "name": name,
                "calories": round((calories / grams) * 100, 2),
                "protein": round((protein / grams) * 100, 2),
                "fat": round((fat / grams) * 100, 2),
                "carbs": round((carbs / grams) * 100, 2),
            })
    return items


def ingest_sqlite(items: list[dict]):
    """Insert via ORM — existing path for local SQLite dev."""
    from src.database import get_db_session
    from src.models import FoodItem

    session = get_db_session()
    session.execute(text("DELETE FROM daily_logs"))
    session.execute(text("DELETE FROM food_items"))
    session.commit()

    food_items = [FoodItem(**item) for item in items]
    session.add_all(food_items)
    session.commit()
    session.close()


def ingest_postgres(items: list[dict]):
    """Insert via raw SQL — bypasses ORM model (which still has integer PKs).

    Postgres tables use UUID PKs (auto-generated by gen_random_uuid()),
    so we insert without specifying id.
    """
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        raise ValueError("SUPABASE_DB_URL not set in environment. Add it to .env")

    engine = create_engine(db_url)
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM daily_logs"))
        conn.execute(text("DELETE FROM food_items"))
        conn.commit()

        conn.execute(
            text("""
                INSERT INTO food_items (name, calories, protein, fat, carbs, source)
                VALUES (:name, :calories, :protein, :fat, :carbs, 'database')
            """),
            items,
        )
        conn.commit()
    engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Ingest nutrition CSV into database")
    parser.add_argument(
        "--target",
        choices=["sqlite", "supabase"],
        default="sqlite",
        help="Target database (default: sqlite)",
    )
    args = parser.parse_args()

    items = parse_csv()
    print(f"Parsed {len(items)} food items from CSV")

    if args.target == "sqlite":
        ingest_sqlite(items)
    else:
        ingest_postgres(items)

    print(f"Ingestion complete! Target: {args.target}, items: {len(items)}")


if __name__ == "__main__":
    main()
```

**Key design decisions**:
- `parse_csv()` extracts pure data logic shared by both targets
- `ingest_sqlite()` uses ORM (`FoodItem` model with integer PK) — unchanged behavior
- `ingest_postgres()` uses raw SQL via `text()` — bypasses ORM model entirely, so `models.py` stays untouched
- `argparse` with `--target` flag, defaults to `sqlite` for backward compatibility
- `engine.dispose()` added for Postgres to clean up connection pool
- Imports for SQLite path (`get_db_session`, `FoodItem`) are inside `ingest_sqlite()` to avoid import errors when only running Postgres path

- **VALIDATE**: `uv run python src/scripts/ingest_simple_db.py --help` shows usage
- **VALIDATE**: `uv run python src/scripts/ingest_simple_db.py --target sqlite` works (regression)

### Task 6: SEED Supabase with Nutrition Data

```bash
uv run python src/scripts/ingest_simple_db.py --target supabase
```

- **VALIDATE** via MCP:
  ```sql
  SELECT count(*) FROM food_items;
  -- Expected: ~335

  SELECT id, name, calories, protein, fat, carbs, source
  FROM food_items LIMIT 5;
  -- Verify: UUIDs as IDs, source='database', values look reasonable

  SELECT count(*) FROM daily_logs;
  -- Expected: 0
  ```

### Task 7: VERIFY Full Schema and Run Regression

**Supabase schema verification** via MCP:
```sql
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'food_items'
ORDER BY ordinal_position;

SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'daily_logs'
ORDER BY ordinal_position;

SELECT indexname, tablename FROM pg_indexes
WHERE tablename IN ('food_items', 'daily_logs');
```

**SQLite regression** — verify local dev still works:
```bash
uv run python src/scripts/ingest_simple_db.py --target sqlite
uv run pytest tests/unit/ -v
```

**Run security advisors** via MCP:
```
mcp__supabase__get_advisors(project_id, type="security")
```

---

## TESTING STRATEGY

### Unit Tests

No new unit tests needed — Step 1 only changes the ETL script and adds remote infrastructure. Existing unit tests must still pass (they use in-memory SQLite).

### Regression

- `uv run pytest tests/unit/ -v` — all existing tests pass
- `uv run python src/scripts/ingest_simple_db.py --target sqlite` — SQLite path unchanged

### Manual Validation

- Supabase dashboard: tables visible, data populated
- MCP SQL queries: row counts, sample data, schema verification

---

## VALIDATION COMMANDS

### Level 1: Dependencies
```bash
uv sync
```

### Level 2: Unit Tests (regression)
```bash
uv run pytest tests/unit/ -v
```

### Level 3: ETL Smoke Test
```bash
uv run python src/scripts/ingest_simple_db.py --target sqlite
uv run python src/scripts/ingest_simple_db.py --target supabase
```

### Level 4: Supabase Verification
Via MCP: `execute_sql` with `SELECT count(*) FROM food_items` — expect ~335

---

## ACCEPTANCE CRITERIA

- [ ] Supabase project created in eu-central-1 (free tier)
- [ ] `food_items` and `daily_logs` tables exist with UUID PKs
- [ ] `food_items` seeded with ~335 nutrition items (source='database')
- [ ] `daily_logs` table exists and is empty
- [ ] Indexes on `food_items.name` and `daily_logs.timestamp`
- [ ] ETL script works with `--target sqlite` (regression)
- [ ] ETL script works with `--target supabase` (new capability)
- [ ] `psycopg2-binary` added to `pyproject.toml`
- [ ] Supabase env vars added to `.env`
- [ ] All existing unit tests pass
- [ ] No changes to graph code, tools, services, or models

---

## NOTES

- **Why raw SQL for Postgres ETL?** The `FoodItem` ORM model has `id: Mapped[int]`. Changing it to UUID is a Step 2/3 concern. Using `text()` SQL for Postgres inserts bypasses this mismatch cleanly.
- **`gen_random_uuid()` vs `uuid-ossp`**: `gen_random_uuid()` is built into Postgres 13+. Supabase also has `uuid-ossp` enabled by default, but the native function is preferred.
- **Session pooler (port 5432)**: Correct for SQLAlchemy which manages its own connection pool. Transaction pooler (6543) doesn't support prepared statements.
- **Supabase password**: Auto-generated during project creation. May need to check dashboard if MCP doesn't return it in the response.
