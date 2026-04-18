# Feature: Food Catalog Migration (Phases A-C)

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Replace the existing food catalog (335 garbage rows from a buggy ETL) with a curated 93-row catalog derived from coach Dolev's nutrition method, and split coach-method-specific data (category, serving size, tag) out of the universal food facts (macros, names, units) into a new `coach_food_mappings` table.

This is **Plan 1 of 3** in the food catalog refactor:

| Plan | Scope |
|---|---|
| **Plan 1 (this doc)** | Schema + models + data wipe + reseed (Phases A-C) |
| Plan 2 (later) | `food_service` refactor — bilingual search, coach mapping joins, unit/serving helpers (Phase D) |
| Plan 3 (later) | Tools + nodes + HITL Hebrew render + prompts (Phases E-F) |

## User Story

As **Dolev** (coach building FitPal),
I want the food catalog to mirror the structure of my coaching method (categories, servings, bilingual names),
So that the bot can correctly identify foods, render them in Hebrew during HITL confirmation, and reason about plan-vs-actual servings instead of raw grams.

## Problem Statement

The current `food_items` table has three blocking deficiencies:

1. **Garbage data** — 335 rows seeded from `data/nutrients_csvfile.csv` via a buggy ETL. 45 rows have CSV section headers glued to the food name (e.g., "Breads, cereals, fastfood,grains - Whole-wheat"), 4 rows have impossible macros (>100g/100g), generic names like "Cheese" / "Beef" confuse the LLM.
2. **No coach-method awareness** — every food is just per-100g macros. The coach's method is built around servings (1 protein serving = 20g protein, 1 carb serving = 50g carbs) and categories (`protein` | `carb` | `free` | `free_calories` | `forbidden_main`). None of this is in the schema, so plan-vs-actual reasoning is impossible.
3. **English-only** — `name` is English; HITL confirmation renders English food names to Hebrew users ("100g Chicken breast" instead of "100 ג׳ חזה עוף").

## Solution Statement

**Two-table split**:
- `food_items` — universal facts (English+Hebrew names, per-100g macros, default unit + unit weight). Coach-agnostic. Same chicken breast row exists regardless of which coach uses it.
- `coach_food_mappings` — opinionated, method-specific. One row per (food, coach) tuple with category, tag, serving_amount_g, notes. Ready to scale to multiple coaches by adding rows, not columns.

**Conservative migration strategy**:
- All schema changes are **additive only** (no renames, no drops). The legacy `name` column stays in place — `food_service.py` keeps querying it during the intermediate state between Plan 1 and Plan 2.
- The new `name_en` column is backfilled by copying `name` into it during the migration.
- The 335 garbage rows get wiped after the schema lands. The 93 canonical rows from `data/canonical_food_catalog.csv` are inserted with corresponding `coach_food_mappings` rows under a single hardcoded `DEFAULT_COACH_ID` (Dolev's auth user UUID).

**System will be in an intentionally degraded state after Plan 1 lands**:
- Bot continues to function in English-only mode (search hits `name`, finds the 93 canonical rows by their English values)
- Hebrew-only inputs will fail to match the catalog and fall through to LLM estimation (acceptable temporary regression)
- Bilingual search, serving-aware HITL, and coach-voice prompts arrive in Plans 2-3
- **Integration tests will partially fail and that's expected** — see Validation Strategy below

## Feature Metadata

**Feature Type**: Refactor (data + schema)
**Estimated Complexity**: Medium
**Primary Systems Affected**: Supabase Postgres schema, `src/models.py`, new seed script
**Dependencies**: Existing canonical catalog at `data/canonical_food_catalog.csv` (already built — 93 rows)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: YOU MUST READ THESE BEFORE IMPLEMENTING

- `src/models.py` (lines 1-103) — current models. `FoodItem` (lines 13-26) needs new columns; `DailyLog` (lines 29-63) is unchanged but the `food_id` FK needs `ON DELETE SET NULL` added in Postgres.
- `docs/patterns/schema-management.md` (the whole file) — DB schema conventions: UUID PKs, `user_id` scoping, audit timestamps, FK rules (auth.users in Postgres only, our own tables in SQLAlchemy), production migrations via Supabase MCP only.
- `src/scripts/ingest_simple_db.py` (lines 1-141) — existing ETL pattern. Sync engine (`psycopg2`), `DELETE FROM` then `INSERT`, raw SQL via `text()`, `--target` argparse. Mirror the structure but **build a new file** (`seed_canonical_catalog.py`) — don't modify the existing script (kept as historical reference).
- `src/database.py` (lines 1-33) — async engine config. Important: SSL workaround for asyncpg to prevent `os.getcwd()` BlockingError. Not needed for the seed script (sync engine), but referenced for context.
- `src/config.py` — needs `DEFAULT_COACH_ID` constant added. Already exports `BASE_DIR`, `USER_TIMEZONE`, `serialize_timestamp`, `get_llm_for_node`.
- `src/services/food_service.py` (lines 47-78) — current search query uses `FoodItem.name.ilike(...)` and `FoodItem.source == "database"`. Plan 1 keeps both columns/values intact so this query continues working. **Do NOT modify this file in Plan 1.**
- `src/services/daily_log_service.py` (the whole file) — does NOT query `food_items` directly. Only operates on `DailyLog`. Plan 1 doesn't touch this service or break its queries.
- `data/canonical_food_catalog.csv` — the 93-row seed source. Headers: `name_en, name_he, category, tag, default_unit, default_unit_weight_g, serving_amount_g, calories_per_100g, protein_per_100g, carbs_per_100g, fat_per_100g, notes`.

### New Files to Create

- `src/scripts/seed_canonical_catalog.py` — async-free seed script that wipes the 335 `database`-source rows, inserts 93 new `food_items` rows, and inserts corresponding `coach_food_mappings` rows. Mirrors `ingest_simple_db.py` patterns (sync engine, raw SQL).

### Files to Update

- `src/models.py` — add 4 new columns to `FoodItem`, add new `CoachFoodMapping` model.
- `src/config.py` — add `DEFAULT_COACH_ID` constant.

### Migrations to Apply (via Supabase MCP)

- One migration: `extend_food_items_and_create_coach_food_mappings` — adds columns to `food_items`, creates `coach_food_mappings` table, alters `daily_logs.food_id` FK to `ON DELETE SET NULL`, enables RLS on the new table.

### Patterns to Follow

**Migration pattern** (from `docs/patterns/schema-management.md` and existing migrations):
- Use `mcp__supabase__apply_migration` with the migration name and SQL body
- ALTER TABLE statements add columns nullable initially (so existing rows don't fail)
- New tables include UUID PK with `gen_random_uuid()` default
- FK constraints to `auth.users` go in Postgres (RLS, ON DELETE CASCADE), NOT in SQLAlchemy models
- Enable RLS on every user-touched table

**Model pattern** (from `docs/patterns/schema-management.md` lines 13-45):
- UUID PK: `mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)`
- Timestamp columns use `DateTime(timezone=True)` with `default=lambda: datetime.now(timezone.utc)` (lambda is mandatory)
- FK between our own tables: declare in SQLAlchemy via `ForeignKey("food_items.id")`
- FK to `auth.users`: do NOT declare in SQLAlchemy; lives in Postgres only
- Index on `user_id`-style scoping columns (here: `coach_id`, `food_id`)

**Seed script pattern** (from `src/scripts/ingest_simple_db.py`):
- Sync engine via `create_engine(db_url)` reading `SUPABASE_DB_URL` env var
- `with engine.connect() as conn` + `conn.execute(text(...))` + `conn.commit()`
- `argparse` with `--target` (sqlite | supabase) — for Plan 1 we only need supabase
- DELETE rows in dependency order (FKs first), then INSERT new data

---

## IMPLEMENTATION PLAN

### Phase A: Schema additions (non-destructive, additive only)

One Supabase migration that does four things:

1. Add `name_en`, `name_he`, `default_unit`, `default_unit_weight_g` columns to `food_items` (all nullable initially)
2. Backfill `name_en` by copying from `name` (so legacy data has both)
3. Create `coach_food_mappings` table (UUID PK, FKs to `food_items.id` and `auth.users(id)`, unique constraint on `(food_id, coach_id)`, RLS enabled)
4. Alter `daily_logs.food_id` FK constraint to `ON DELETE SET NULL` (so wiping food_items doesn't fail or destroy daily_logs rows — their denormalized macros survive)

The legacy `name` column **stays** — this is what allows `food_service.py` to keep functioning between Plan 1 and Plan 2.

### Phase B: SQLAlchemy models + config

- Update `FoodItem` in `src/models.py` to declare the new columns (all `Optional`)
- Add new `CoachFoodMapping` model following the schema-management template
- Add `DEFAULT_COACH_ID` constant in `src/config.py` — set to Dolev's auth user UUID. **Implementer must query Supabase to find Dolev's user UUID** (`SELECT id FROM auth.users WHERE email LIKE '%dolev%'` or by looking at the food_items.user_id values for estimated rows that the user identifies as theirs). Document the chosen UUID in a code comment.

### Phase C: Data wipe + reseed

- Build `src/scripts/seed_canonical_catalog.py`:
  1. Read `data/canonical_food_catalog.csv` into a list of dicts
  2. Open sync connection to `SUPABASE_DB_URL`
  3. `DELETE FROM coach_food_mappings` (clean slate; table is brand new but be defensive in case of re-runs)
  4. `DELETE FROM food_items WHERE source = 'database'` (CASCADE SET NULL handles daily_logs.food_id)
  5. For each CSV row: `INSERT INTO food_items` (returning id), then `INSERT INTO coach_food_mappings` with the captured food_id + `DEFAULT_COACH_ID` (only when `category` is non-empty AND when `serving_amount_g` is meaningful — see Edge Cases below)
  6. Commit
- Run the script once
- Verify via DB-level SQL queries (see Validation)

### What Plan 1 does NOT do

- **No changes to `src/services/food_service.py`** — covered by Plan 2
- **No changes to any node, tool, or prompt** — covered by Plans 2-3
- **No removal of the `name` column on food_items** — covered by Plan 2 (after services migrate to `name_en`)
- **No integration tests added or run** — see Validation Strategy

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### Task 1 — VERIFY Dolev's auth user UUID

- **IMPLEMENT**: Confirm that `71a8c873-c6bd-498e-a6ca-bd27d6118329` exists in `auth.users` and corresponds to Dolev's production Telegram identity (`275939731@telegram.fitpal.bot`). This UUID was selected during planning as the canonical `DEFAULT_COACH_ID` for the POC.
- **PATTERN**: This UUID gets hardcoded into `src/config.py` in Task 4 and referenced by the seed script in Task 5.
- **GOTCHA**: Do not change the UUID without re-confirming with Dolev. The dev user (`ae521c1a-d814-4b44-81df-aef446b672ea`), Studio default (`fbeeb45f-d728-4c7c-9e6d-7b9b41685da7`), and E2E test user (`72c10336-9d61-4357-9851-20cbb4d32b1a`) all exist but were intentionally not selected — production identity is safest from accidental cleanup.
- **VALIDATE**:
  ```sql
  SELECT id, email FROM auth.users
  WHERE id = '71a8c873-c6bd-498e-a6ca-bd27d6118329';
  ```
  Expect exactly 1 row with email `275939731@telegram.fitpal.bot`.

### Task 2 — APPLY Supabase migration

- **IMPLEMENT**: Use `mcp__supabase__apply_migration` with name `extend_food_items_and_create_coach_food_mappings` and the SQL body below.
- **PATTERN**: Mirrors existing migrations like `add_user_id_columns` and `add_nutrition_plan_to_user_profiles`. Additive only, no destructive ALTERs.
- **IMPORTS**: N/A (raw SQL via MCP)
- **GOTCHA**: The `daily_logs.food_id` FK constraint name is `daily_logs_food_id_fkey` (verified via `pg_constraint` query). If it differs, the migration's DROP CONSTRAINT will fail — re-query first.
- **VALIDATE**:
  - `SELECT column_name FROM information_schema.columns WHERE table_name = 'food_items' AND column_name IN ('name_en', 'name_he', 'default_unit', 'default_unit_weight_g');` → expect 4 rows
  - `SELECT to_regclass('public.coach_food_mappings');` → expect non-null
  - `SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'daily_logs_food_id_fkey';` → expect `ON DELETE SET NULL` substring
  - `SELECT COUNT(*) FROM food_items WHERE name_en IS NOT NULL;` → expect 355 (all current rows backfilled)

**SQL body:**
```sql
-- Phase A.1: Add new columns to food_items (nullable initially)
ALTER TABLE food_items
  ADD COLUMN name_en TEXT,
  ADD COLUMN name_he TEXT,
  ADD COLUMN default_unit TEXT,
  ADD COLUMN default_unit_weight_g DOUBLE PRECISION;

-- Phase A.2: Backfill name_en from existing name column
UPDATE food_items SET name_en = name WHERE name_en IS NULL;

-- Phase A.3: Indexes for bilingual search (used by Plan 2)
CREATE INDEX IF NOT EXISTS idx_food_items_name_en ON food_items (name_en);
CREATE INDEX IF NOT EXISTS idx_food_items_name_he ON food_items (name_he);

-- Phase A.4: Create coach_food_mappings table
CREATE TABLE coach_food_mappings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  food_id UUID NOT NULL REFERENCES food_items(id) ON DELETE CASCADE,
  coach_id UUID NOT NULL,
  category TEXT NOT NULL CHECK (category IN ('protein', 'carb', 'fat', 'free', 'free_calories', 'forbidden_main')),
  tag TEXT CHECK (tag IS NULL OR tag IN ('lean', 'medium', 'fatty')),
  serving_amount_g DOUBLE PRECISION,
  notes TEXT,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ,
  UNIQUE (food_id, coach_id)
);

CREATE INDEX idx_coach_food_mappings_food_id ON coach_food_mappings (food_id);
CREATE INDEX idx_coach_food_mappings_coach_id ON coach_food_mappings (coach_id);

-- FK to auth.users (Postgres-only per schema-management.md)
ALTER TABLE coach_food_mappings
  ADD CONSTRAINT fk_coach_food_mappings_coach_id
  FOREIGN KEY (coach_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Phase A.5: RLS on coach_food_mappings
ALTER TABLE coach_food_mappings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access" ON coach_food_mappings
  AS PERMISSIVE FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Authenticated users can read" ON coach_food_mappings
  AS PERMISSIVE FOR SELECT TO authenticated
  USING (true);

-- Phase A.6: Switch daily_logs.food_id FK to ON DELETE SET NULL
-- (so wiping food_items in Phase C doesn't cascade-fail or destroy daily_logs rows)
ALTER TABLE daily_logs DROP CONSTRAINT IF EXISTS daily_logs_food_id_fkey;
ALTER TABLE daily_logs
  ADD CONSTRAINT daily_logs_food_id_fkey
  FOREIGN KEY (food_id) REFERENCES food_items(id) ON DELETE SET NULL;
```

### Task 3 — UPDATE `src/models.py`

- **IMPLEMENT**: Add 4 new columns to `FoodItem`. Add new `CoachFoodMapping` model after `FoodItem`. Add the `CoachFoodMapping` import to anywhere that imports models (no callers exist yet — services don't reference it until Plan 2).
- **PATTERN**: Mirror the model template from `docs/patterns/schema-management.md` lines 13-45. Existing `FoodItem` is the closest example.
- **IMPORTS** (already in file): `import uuid as uuid_mod`, `from datetime import datetime, timezone`, `from typing import Optional`, `from sqlalchemy import Uuid, String, Float, Integer, DateTime, Text, ForeignKey, Boolean`, `from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column`. **Add**: `Boolean` to the existing sqlalchemy import line.
- **GOTCHA**: Keep the legacy `name` column on `FoodItem`. Do NOT rename it to `name_en` in the model. If you remove `name`, `food_service.py` queries break and Plan 1 stops being additive-only.
- **VALIDATE**: `uv run python -c "from src.models import FoodItem, CoachFoodMapping; print(FoodItem.__table__.columns.keys()); print(CoachFoodMapping.__table__.columns.keys())"` → expect `name`, `name_en`, `name_he`, `default_unit`, `default_unit_weight_g` in FoodItem and the full `CoachFoodMapping` columns list.

**Model additions (full text for `FoodItem` extensions):**
```python
class FoodItem(Base):
    __tablename__ = "food_items"

    id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)  # Legacy — kept until Plan 2 migrates services
    name_en: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    name_he: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    calories: Mapped[Optional[float]] = mapped_column(Float)
    protein: Mapped[Optional[float]] = mapped_column(Float)
    fat: Mapped[Optional[float]] = mapped_column(Float)
    carbs: Mapped[Optional[float]] = mapped_column(Float)
    default_unit: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    default_unit_weight_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False, server_default="database")
    user_id: Mapped[Optional[uuid_mod.UUID]] = mapped_column(Uuid, nullable=True, index=True)

    logs: Mapped[list["DailyLog"]] = relationship("DailyLog", back_populates="food_item")
    coach_mappings: Mapped[list["CoachFoodMapping"]] = relationship(
        "CoachFoodMapping", back_populates="food_item", cascade="all, delete-orphan"
    )
```

**New `CoachFoodMapping` model (append after `FoodItem`):**
```python
class CoachFoodMapping(Base):
    """Coach-method-specific overlay on top of universal food data.
    One row per (food_id, coach_id) tuple — multiple coaches can map the same food
    differently (different categories, different serving sizes per their methods).
    """

    __tablename__ = "coach_food_mappings"

    id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)
    food_id: Mapped[uuid_mod.UUID] = mapped_column(
        Uuid, ForeignKey("food_items.id"), nullable=False, index=True
    )
    coach_id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String, nullable=False)  # CHECK constraint enforced in Postgres
    tag: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    serving_amount_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    food_item: Mapped["FoodItem"] = relationship("FoodItem", back_populates="coach_mappings")

    __table_args__ = (UniqueConstraint("food_id", "coach_id", name="uq_coach_food_mappings_food_coach"),)
```

Note: `UniqueConstraint` is a new import — add to the sqlalchemy import line: `from sqlalchemy import Uuid, String, Float, Integer, DateTime, Text, ForeignKey, Boolean, UniqueConstraint`.

### Task 4 — ADD `DEFAULT_COACH_ID` to `src/config.py`

- **IMPLEMENT**: Add a module-level constant set to Dolev's production user UUID (verified in Task 1):
  ```python
  import uuid

  # Single-coach POC fallback. Maps to Dolev's production Telegram user
  # (275939731@telegram.fitpal.bot). When we extend to multiple coaches,
  # replace this constant with a coaches-table lookup.
  DEFAULT_COACH_ID = uuid.UUID("71a8c873-c6bd-498e-a6ca-bd27d6118329")
  ```
- **PATTERN**: Other module-level constants in `src/config.py` (e.g., `USER_TIMEZONE`, `BASE_DIR`) — same style.
- **IMPORTS**: `import uuid` at top of `src/config.py` if not already present.
- **GOTCHA**: This UUID is referenced by the seed script in Task 5 and (in Plan 2) by `food_service` joins. Don't change the value without updating both consumers.
- **VALIDATE**: `uv run python -c "from src.config import DEFAULT_COACH_ID; print(DEFAULT_COACH_ID, type(DEFAULT_COACH_ID))"` → expect `71a8c873-c6bd-498e-a6ca-bd27d6118329` and the `uuid.UUID` type.

### Task 5 — CREATE `src/scripts/seed_canonical_catalog.py`

- **IMPLEMENT**: New seed script that wipes `database`-source rows and inserts 93 canonical foods + their coach mappings.
- **PATTERN**: Mirror `src/scripts/ingest_simple_db.py` — sync engine, raw SQL via `text()`, env var via `load_dotenv()`. Don't use `Base.metadata.create_all()` (the migration handles schema; per `docs/patterns/schema-management.md` rule 7, never `create_all` against production).
- **IMPORTS**: `import argparse`, `import csv`, `import os`, `import sys`, `from pathlib import Path`, `from dotenv import load_dotenv`, `from sqlalchemy import create_engine, text`, `from src.config import BASE_DIR, DEFAULT_COACH_ID`.
- **GOTCHA**: 
  - The CSV has empty values for some fields (`tag`, `serving_amount_g`, `notes`, `default_unit_weight_g`) — convert empty strings to NULL when inserting, not 0 or empty string.
  - Free-category items have empty `serving_amount_g` (vegetables aren't counted). Still create a `coach_food_mappings` row with `serving_amount_g = NULL` so the food has its category attached.
  - Forbidden-main items also have empty `serving_amount_g` — same treatment.
  - **Do NOT delete `source = 'estimated'` rows** — those are real user data with their own `user_id`. Only wipe `source = 'database'`.
  - The migration created `name_en`/`name_he` indexes — inserts will be slightly slower with indexes, but 93 rows is trivial.
  - Keep the legacy `name` column populated (set `name = name_en` for the new rows so old code paths continue working).
- **VALIDATE**:
  - `uv run python src/scripts/seed_canonical_catalog.py --target supabase` exits 0
  - `SELECT COUNT(*) FROM food_items WHERE source = 'database';` → expect 93
  - `SELECT COUNT(*) FROM coach_food_mappings;` → expect 93
  - `SELECT COUNT(*) FROM food_items WHERE source = 'estimated';` → expect 20 (untouched)

**Script structure (full text):**
```python
import argparse
import csv
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from src.config import BASE_DIR, DEFAULT_COACH_ID

load_dotenv()

CSV_PATH = os.path.join(BASE_DIR, "data", "canonical_food_catalog.csv")


def _empty_to_none(value: str):
    """Convert empty string to None; preserve other values as-is."""
    return None if value == "" or value is None else value


def _to_float(value):
    """Convert string to float, or None if empty."""
    v = _empty_to_none(value)
    return float(v) if v is not None else None


def parse_csv() -> list[dict]:
    """Parse the canonical food catalog CSV. Returns one dict per row."""
    items = []
    with open(CSV_PATH, mode='r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            items.append({
                "name_en": row["name_en"].strip(),
                "name_he": _empty_to_none(row["name_he"].strip()) if row["name_he"] else None,
                "category": _empty_to_none(row["category"].strip()),
                "tag": _empty_to_none(row["tag"].strip()) if row["tag"] else None,
                "default_unit": _empty_to_none(row["default_unit"].strip()) if row["default_unit"] else None,
                "default_unit_weight_g": _to_float(row["default_unit_weight_g"]),
                "serving_amount_g": _to_float(row["serving_amount_g"]),
                "calories": _to_float(row["calories_per_100g"]),
                "protein": _to_float(row["protein_per_100g"]),
                "carbs": _to_float(row["carbs_per_100g"]),
                "fat": _to_float(row["fat_per_100g"]),
                "notes": _empty_to_none(row["notes"].strip()) if row["notes"] else None,
            })
    return items


def seed_supabase(items: list[dict]):
    """Wipe `database`-source rows and reseed from canonical catalog."""
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        raise ValueError("SUPABASE_DB_URL not set in environment. Add it to .env")

    engine = create_engine(db_url)
    with engine.connect() as conn:
        # Wipe in dependency order — coach_food_mappings cascades on food_items delete,
        # but be defensive in case the script reruns and previous mappings linger
        conn.execute(text("DELETE FROM coach_food_mappings WHERE coach_id = :coach_id"),
                     {"coach_id": str(DEFAULT_COACH_ID)})
        conn.execute(text("DELETE FROM food_items WHERE source = 'database'"))
        conn.commit()

        for item in items:
            # Insert food_items row, capture id
            food_result = conn.execute(
                text("""
                    INSERT INTO food_items (name, name_en, name_he, calories, protein, fat, carbs,
                                            default_unit, default_unit_weight_g, source)
                    VALUES (:name_en, :name_en, :name_he, :calories, :protein, :fat, :carbs,
                            :default_unit, :default_unit_weight_g, 'database')
                    RETURNING id
                """),
                {
                    "name_en": item["name_en"],
                    "name_he": item["name_he"],
                    "calories": item["calories"],
                    "protein": item["protein"],
                    "fat": item["fat"],
                    "carbs": item["carbs"],
                    "default_unit": item["default_unit"],
                    "default_unit_weight_g": item["default_unit_weight_g"],
                },
            )
            food_id = food_result.scalar_one()

            # Insert coach_food_mappings row (every food gets a mapping; serving_amount_g may be NULL)
            if item["category"] is not None:
                conn.execute(
                    text("""
                        INSERT INTO coach_food_mappings (food_id, coach_id, category, tag,
                                                          serving_amount_g, notes)
                        VALUES (:food_id, :coach_id, :category, :tag, :serving_amount_g, :notes)
                    """),
                    {
                        "food_id": str(food_id),
                        "coach_id": str(DEFAULT_COACH_ID),
                        "category": item["category"],
                        "tag": item["tag"],
                        "serving_amount_g": item["serving_amount_g"],
                        "notes": item["notes"],
                    },
                )

        conn.commit()
    engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Seed canonical food catalog into Supabase")
    parser.add_argument(
        "--target",
        choices=["supabase"],
        default="supabase",
        help="Target database (only supabase supported)",
    )
    args = parser.parse_args()

    items = parse_csv()
    print(f"Parsed {len(items)} food items from canonical catalog")

    seed_supabase(items)
    print(f"Seed complete. Inserted {len(items)} food_items + {sum(1 for i in items if i['category'])} coach_food_mappings.")


if __name__ == "__main__":
    main()
```

### Task 6 — RUN the seed script

- **IMPLEMENT**: `uv run python src/scripts/seed_canonical_catalog.py --target supabase`
- **GOTCHA**: This is a destructive operation against production Supabase. Confirm with Dolev before running. The "no DB mutations without explicit approval" rule applies.
- **VALIDATE**: See Validation Commands section below.

---

## TESTING STRATEGY

**Plan 1 deliberately does NOT add or run integration tests.** The reason:

- After Plan 1 lands, `food_service.py` still queries `FoodItem.name` and `source = 'database'`
- That query now finds 93 canonical rows instead of 335 garbage ones
- Existing integration tests that depend on specific food names being present (e.g., a test that searches for "chicken" expecting the legacy `chicken` row with macros 217.65/27.06/10.59) **will fail** because the legacy data is gone and the new row is `Chicken breast` with different per-100g values
- This is **expected and acceptable** — the integration test suite resumes passing after Plan 2 ships the bilingual search and tests get updated to reference the new canonical row names

**What we test in Plan 1**: DB-level state via SQL queries (see Validation Commands). That's it. Skip:

- ❌ `uv run pytest tests/integration/` (will partially fail by design)
- ❌ `uv run pytest tests/graph_api/` (depends on services + integration data being valid)
- ❌ Adding any new Python tests

**What we add to test in Plan 2**: bilingual search tests, coach mapping join tests, unit resolution helper tests. Plan 2 is also the right time to update the legacy integration tests that depended on removed seed data.

### Edge Cases to Verify Manually (DB-level)

- Old `daily_logs` rows with `food_id` pointing at deleted `food_items` rows now have `food_id = NULL` (their denormalized macros remain intact)
- The 20 `source = 'estimated'` rows are untouched (real user data preserved)
- Each of the 93 inserted `food_items` has a corresponding `coach_food_mappings` row (categories like `free` and `forbidden_main` get rows even when `serving_amount_g` is NULL)
- Hebrew names appear in `name_he` for the relevant rows (the catalog has Hebrew for all 93 rows)
- The `daily_logs.food_id` FK now reads `ON DELETE SET NULL`

---

## VALIDATION COMMANDS

Execute every command in order. Each verifies a specific post-condition.

### Level 1: Syntax & Style

```bash
# Lint the seed script and updated models
uv run ruff check src/models.py src/config.py src/scripts/seed_canonical_catalog.py

# Type-check the modified files
uv run python -c "from src.models import FoodItem, CoachFoodMapping; from src.config import DEFAULT_COACH_ID; print('imports OK')"
```

### Level 2: Unit Tests

```bash
# Run the existing unit suite — should still pass (no service code changed in Plan 1)
uv run pytest tests/unit/ -v
```

Expected: all unit tests pass. If any unit test depends on `FoodItem.name` only and fails because the model now has `name_en`/`name_he`, that's a sign Task 3 was implemented incorrectly (the legacy `name` column must remain).

### Level 3: Integration Tests

**SKIP THIS LEVEL FOR PLAN 1.** Integration tests will fail because they depend on either (a) specific seed data names that no longer exist, or (b) `food_service.py` returning shapes that haven't been refactored yet. Resume integration testing in Plan 2.

### Level 4: DB-Level Manual Validation

Run each query via `mcp__supabase__execute_sql` (or `psql`). Each should return the expected result.

```sql
-- 1. Schema additions present
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'food_items'
  AND column_name IN ('name', 'name_en', 'name_he', 'default_unit', 'default_unit_weight_g')
ORDER BY column_name;
-- Expect 5 rows (name + 4 new columns)

-- 2. coach_food_mappings table exists with correct shape
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'coach_food_mappings'
ORDER BY ordinal_position;
-- Expect 10 columns

-- 3. FK constraint on daily_logs.food_id is ON DELETE SET NULL
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname = 'daily_logs_food_id_fkey';
-- Expect: FOREIGN KEY (food_id) REFERENCES food_items(id) ON DELETE SET NULL

-- 4. Row counts after seed
SELECT source, COUNT(*) FROM food_items GROUP BY source ORDER BY source;
-- Expect: database = 93, estimated = 20

-- 5. Coach mappings populated
SELECT COUNT(*) FROM coach_food_mappings;
-- Expect: 93 (every CSV row has a category, so every row gets a mapping)

-- 6. Coach mappings reference Dolev's user_id
SELECT DISTINCT coach_id::text FROM coach_food_mappings;
-- Expect: 1 row matching DEFAULT_COACH_ID

-- 7. All categories represented
SELECT category, COUNT(*) FROM coach_food_mappings GROUP BY category ORDER BY category;
-- Expect roughly: protein=28, carb=7, free=13, free_calories=16, forbidden_main=11

-- 8. Hebrew names populated for canonical rows
SELECT COUNT(*) FROM food_items
WHERE source = 'database' AND name_he IS NOT NULL;
-- Expect: 93

-- 9. Old daily_logs that pointed at deleted foods now have food_id = NULL
-- (denormalized macros preserved — calories/protein/etc are still intact)
SELECT COUNT(*) FROM daily_logs WHERE food_id IS NULL;
-- Expect: a positive number reflecting old logs whose food was wiped

-- 10. No estimated foods were touched
SELECT COUNT(*) FROM food_items WHERE source = 'estimated';
-- Expect: 20 (unchanged from pre-migration)

-- 11. No food_items orphaned in coach_food_mappings (FK integrity)
SELECT COUNT(*) FROM coach_food_mappings cfm
LEFT JOIN food_items fi ON fi.id = cfm.food_id
WHERE fi.id IS NULL;
-- Expect: 0

-- 12. Sample row sanity check
SELECT fi.name_en, fi.name_he, cfm.category, cfm.tag, cfm.serving_amount_g
FROM food_items fi
JOIN coach_food_mappings cfm ON cfm.food_id = fi.id
WHERE fi.source = 'database' AND fi.name_en = 'Chicken breast';
-- Expect: name_en='Chicken breast', name_he='חזה עוף', category='protein', tag='lean', serving_amount_g=100
```

---

## ACCEPTANCE CRITERIA

- [ ] Migration `extend_food_items_and_create_coach_food_mappings` applied successfully
- [ ] `food_items` has 4 new columns (`name_en`, `name_he`, `default_unit`, `default_unit_weight_g`), all `NULL`-able initially
- [ ] All pre-existing rows have `name_en` populated (copied from `name`)
- [ ] `coach_food_mappings` table exists with the correct schema, RLS enabled, FKs in place
- [ ] `daily_logs.food_id` FK now uses `ON DELETE SET NULL`
- [ ] `src/models.py` has `FoodItem` extensions and new `CoachFoodMapping` class
- [ ] `src/config.py` exports `DEFAULT_COACH_ID` (Dolev's auth UUID)
- [ ] `src/scripts/seed_canonical_catalog.py` exists and runs cleanly
- [ ] After seed: 93 `food_items` rows with `source = 'database'`, 20 with `source = 'estimated'`, 93 `coach_food_mappings` rows
- [ ] Old `daily_logs.food_id` references that pointed at wiped rows are now `NULL` (macros intact)
- [ ] All 12 DB-level validation queries return expected results
- [ ] Unit tests still pass (`uv run pytest tests/unit/ -v`)
- [ ] **No code changes outside the files listed in this plan** (no service refactor, no node updates, no prompt changes)

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Migration SQL applied via `mcp__supabase__apply_migration`
- [ ] `src/models.py` updated and imports cleanly
- [ ] `src/config.py` updated with `DEFAULT_COACH_ID`
- [ ] Seed script created and executed
- [ ] All 12 DB-level validation queries verified
- [ ] Unit tests pass
- [ ] Integration tests **NOT** run (intentional)
- [ ] Successor work section reviewed by Dolev — confirm schema is sufficient for Plans 2 and 3

---

## SUCCESSOR WORK

This section is **not implementation detail**. Its purpose is to verify that the schema delivered in Plan 1 is sufficient for what Plans 2 and 3 will need. If a successor item is checked off as "schema sufficient", we're done. If not, Plan 1 needs amending.

### Plan 2 — `food_service` refactor (Phase D)

| Need | Schema sufficient? | Why |
|---|---|---|
| Bilingual search (match Hebrew or English input) | ✅ | `name_en` and `name_he` columns + indexes both exist |
| Return coach mapping data alongside food | ✅ | `coach_food_mappings` joins via `food_id`, returns `category`/`tag`/`serving_amount_g`/`notes` |
| Resolve unit-based amounts ("2 eggs" → 100g) | ✅ | `default_unit` + `default_unit_weight_g` columns on `food_items` provide the per-unit weight |
| Compute serving counts (amount_g ÷ serving_amount_g) | ✅ | `serving_amount_g` is on `coach_food_mappings` |
| Drop `name` column once services migrate | ⚠️ Plan 2 will need a follow-up migration to drop `name` after `food_service.py` migrates queries to `name_en` |

### Plan 3 — Tools + nodes + HITL + prompts (Phases E-F)

| Need | Schema sufficient? | Why |
|---|---|---|
| HITL renders Hebrew name when `BOT_LANGUAGE=he` | ✅ | `name_he` is on `food_items`, populated for all 93 canonical rows |
| HITL shows serving count alongside grams | ✅ | Plan 2 returns `serving_amount_g`; tool surfaces it; node renders it |
| Response node reasons over remaining servings per category | ✅ | `category` on `coach_food_mappings` enables grouping |
| Estimation path classifies new foods into a category | ⚠️ Plan 3 needs a UX decision: does estimation surface a guessed `category` to the user during HITL, or run a separate classification step? Schema supports either approach (just insert into `coach_food_mappings` post-HITL). |
| Lean/medium/fatty recommendations in coach voice | ✅ | `tag` column carries this signal |

**Bottom line: schema is sufficient.** Two soft items flagged (drop legacy `name`, decide estimation classification UX) are downstream work, not gaps.

---

## NOTES

### Why we kept the legacy `name` column

The schema design we agreed on conceptually replaces `name` with `name_en`. But in Plan 1 we keep `name` because:
- `food_service.py` queries `FoodItem.name.ilike(...)` — refactoring this is Plan 2's job
- Removing `name` in Plan 1 would force-break the bot at the SQLAlchemy ORM layer (AttributeError on `FoodItem.name`)
- Keeping it lets the bot stay functional in English-only mode between Plan 1 and Plan 2 (degraded but not broken)
- Plan 2 ships a follow-up migration that drops `name` after services migrate

### Why the seed script doesn't use the SQLAlchemy ORM

`docs/patterns/schema-management.md` rule 7 forbids `Base.metadata.create_all()` against production. The existing `ingest_simple_db.py` for Postgres uses raw SQL via `text()` for the same reason. We mirror that pattern — schema lives in the migration, the seed script only manipulates rows.

### Why we delete `coach_food_mappings` defensively

The migration creates the table empty, so `DELETE FROM coach_food_mappings` is a no-op on the first run. But if the seed script is rerun (e.g., to refresh data after editing the CSV), we want the existing mappings cleared first. Hence the defensive delete scoped by `coach_id = DEFAULT_COACH_ID`.

### Risk: someone runs the seed before applying the migration

Mitigation: the script will fail with a clear "column does not exist" or "relation does not exist" error from Postgres. No data corruption. Fix: apply the migration first.

### Confidence: 8/10 for one-pass success

Implementation risks:
- The exact UUID for Dolev's auth user requires a manual lookup + confirmation step (Task 1)
- The FK constraint name on `daily_logs.food_id` is verified as `daily_logs_food_id_fkey` but a re-check before the migration is wise
- CSV parsing must correctly handle empty values for `tag`, `serving_amount_g`, `notes`, `default_unit_weight_g` (helper functions provided)

What could go wrong:
- If a coach mapping insert fails mid-loop, partial state remains. Wrapping the per-row insert in a transaction-per-row instead of one big transaction limits blast radius. The provided script uses one transaction per food + mapping pair (auto-committed by `with engine.connect() as conn` block — actually it's one big transaction). If preferred, restructure to commit per item — but at 93 rows, the all-or-nothing approach is simpler and appropriate for a seed script.
