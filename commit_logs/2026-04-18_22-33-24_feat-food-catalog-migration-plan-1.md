# feat: food catalog migration — Plan 1 (schema + models + reseed)

**Date**: 2026-04-18
**Branch**: `refine_prompts_and_evals`
**Plan**: `docs/plans/food-catalog-migration.md` (Plan 1 of 3)

## Context

The `food_items` table had three blocking deficiencies:

1. **Garbage data** — 335 rows seeded from `data/nutrients_csvfile.csv` via a buggy ETL. 45 rows had CSV section headers glued to the food name, 4 rows had impossible macros (>100g/100g), generic names like "Cheese" / "Beef" confused the LLM during search.
2. **No coach-method awareness** — every food was just per-100g macros. The coach's method is built around servings (1 protein serving = 20g protein, 1 carb serving = 50g carbs) and categories (`protein` | `carb` | `free` | `free_calories` | `forbidden_main`). None of this lived in the schema, blocking plan-vs-actual reasoning.
3. **English-only** — `name` was English; HITL confirmation rendered English food names to Hebrew users.

Plan 1 lays the foundation: extends `food_items` with bilingual + unit columns, creates a new `coach_food_mappings` table for opinionated method-specific data, wipes the 335 garbage rows, reseeds with 93 curated rows derived from Dolev's bulk plan + cut plan + real user logs.

## Changes

### Schema (Supabase migration: `extend_food_items_and_create_coach_food_mappings`)

- `food_items` extended with 4 new columns (all nullable initially): `name_en`, `name_he`, `default_unit`, `default_unit_weight_g`
- Backfilled `name_en` from existing `name` column for all 355 pre-existing rows
- Added indexes on `name_en` and `name_he` for upcoming bilingual search (Plan 2)
- Created `coach_food_mappings` table with:
  - `food_id` FK to `food_items` (CASCADE delete)
  - `coach_id` FK to `auth.users` (Postgres-only per `docs/patterns/schema-management.md`)
  - `category` (CHECK constraint: protein | carb | fat | free | free_calories | forbidden_main)
  - `tag` (CHECK constraint: lean | medium | fatty | NULL)
  - `serving_amount_g`, `notes`, `active`, audit timestamps
  - Unique constraint on (food_id, coach_id)
  - RLS enabled (service role full access, authenticated users read-only)
- Switched `daily_logs.food_id` FK from default `NO ACTION` to `ON DELETE SET NULL` so wiping food_items doesn't cascade-fail or destroy logs (their denormalized macros survive intact)

### `src/models.py`

- Added 4 new columns to `FoodItem` (mirrors the migration); kept legacy `name` column intact so `food_service.py` continues working until Plan 2
- Added `CoachFoodMapping` model following `docs/patterns/schema-management.md` template (UUID PK, audit timestamps, FK relationship back-reference)
- Added `Boolean`, `UniqueConstraint` to the sqlalchemy import line

### `src/config.py`

- Added `DEFAULT_COACH_ID = uuid.UUID("71a8c873-c6bd-498e-a6ca-bd27d6118329")` — Dolev's production Telegram user. Single-coach POC fallback; replaces with a coaches table when multi-coach support lands.

### `src/scripts/seed_canonical_catalog.py` (new)

- Reads `data/canonical_food_catalog.csv` (93 rows; gitignored — see Notes)
- Wipes `coach_food_mappings` for `DEFAULT_COACH_ID`, then `food_items WHERE source = 'database'`
- For each CSV row: inserts `food_items` (capturing id), then inserts paired `coach_food_mappings` row
- Sets legacy `name` = `name_en` so the still-unmigrated `food_service.py` keeps finding rows by English name
- Mirrors the existing `ingest_simple_db.py` pattern (sync engine, raw SQL via `text()`, `--target supabase`)

### `docs/plans/food-catalog-migration.md` (new)

Full Plan 1 doc — DDL, code diffs, validation queries, successor work verification.

## Validation

DB-level only (integration tests intentionally skipped — see "Why integration tests skipped" below):

| Check | Expected | Actual |
|---|---|---|
| `food_items` source=database | 93 | **93** ✅ |
| `food_items` source=estimated (untouched) | 20 | **20** ✅ |
| `coach_food_mappings` rows | 93 | **93** ✅ |
| Distinct coach_id | 1 | **1** ✅ |
| Hebrew names populated | 93 | **93** ✅ |
| Orphan mappings (FK integrity) | 0 | **0** ✅ |
| `daily_logs.food_id` nulled (CASCADE worked) | >0 | **32** ✅ |
| Category distribution | matches plan | protein=43, free_calories=15, free=14, forbidden_main=12, carb=9 ✅ |
| Sample row (Chicken breast) end-to-end | name_he=חזה עוף, serving=100g, lean | ✅ |

Unit tests: **130 passed** (`uv run pytest tests/unit/`).

### Why integration tests skipped

Plan 1 is intentionally additive to the schema but does NOT update services. After this commit:
- `food_service.search_food_items` still queries `FoodItem.name` — keeps working because `name` column is preserved + populated via `name = name_en` during seed
- The 335 garbage rows are gone, so any integration test referencing legacy seed names (e.g., `chicken` lowercase with macros 217.65/27.06/10.59) will fail
- This is the documented intermediate state. Integration tests resume in Plan 2 after services migrate.

## Next steps

### Plan 2 — `food_service` refactor (Phase D)

Mid-sized refactor of `src/services/food_service.py` (~190 lines today):

1. **Bilingual search** — switch `search_food_items` from `FoodItem.name.ilike(...)` to `FoodItem.name_en.ilike(...) OR FoodItem.name_he.ilike(...)` with the bilingual indexes added in Plan 1
2. **Coach mapping join** — every food fetch returns the corresponding `coach_food_mappings` row (category, tag, serving_amount_g) under `DEFAULT_COACH_ID`. New service signature returns a richer dict.
3. **Unit resolution helper** — new `resolve_amount_g(food, unit, count)` that converts "2 eggs" → 100g using `default_unit_weight_g`
4. **Serving count helper** — new `compute_servings(amount_g, mapping)` for plan-vs-actual math
5. **`create_food_item` signature update** — accept `name_en`, `name_he`, `default_unit`, `default_unit_weight_g`
6. **Drop the input parser's English translation hack** — Plan 2's bilingual search makes it obsolete; parser stays generic and emits whatever language the user typed
7. **Schema follow-up migration** — once services no longer reference the legacy `name` column, drop it (`ALTER TABLE food_items DROP COLUMN name`)
8. **Update integration tests** — adjust references to legacy seed names that no longer exist; add coverage for bilingual search and coach mapping join

### Plan 3 — Tools + nodes + HITL + prompts (Phases E + F)

Tightly coupled — better tackled together than split:

1. **Tool signatures** — `search_food`, `calculate_food_macros`, `create_food_item` surface the new fields (category, tag, serving counts, Hebrew name)
2. **`confirmation_node` HITL render** — render `name_he` when `BOT_LANGUAGE=he`, show serving count alongside grams (e.g., "2 ביצים (100 ג׳, ~0.7 מנת חלבון)")
3. **`calculate_macros_node`** — consume the new tool output shape; pass serving info downstream
4. **Estimation path UX decision** — when LLM estimates a new food, surface guessed `category` to user during HITL OR run a separate classification step? Decide at design time, schema supports either.
5. **Prompt updates**:
   - `input_parser` — extract `{unit, count}` instead of just `amount_g`; drop the English translation requirement
   - `response_node` — coach voice with serving math ("you have 30g protein left = ~1.5 servings"), reference `category` and `tag` from coach mappings
6. **HITL Hebrew copy** — exact wording for confirmation prompts in Hebrew (rendering format TBD with real data in front of us)

### Immediate follow-up (smaller items)

- **Decide on CSV tracking**: `data/canonical_food_catalog.csv` is gitignored along with the rest of `data/`. If anyone needs to reseed (new dev env, recovery), the file must be reconstructed. Two options: (a) carve out an exception in `.gitignore` for this specific file since it's the canonical source-of-truth, (b) treat the Supabase DB as the only source and accept the reseed-from-scratch cost. Defer until it bites.
- **Coach plan ingestion flow**: as Dolev edits or expands his bulk/cut plans, how do new foods get into the catalog + coach mappings? Today: edit CSV, rerun seed script. Future: a coach UI or skill that updates rows in place. Out of scope for Plans 2-3.

## Notes

### Migration was non-destructive (additive only)

The schema migration added columns, created a new table, and changed a FK CASCADE rule. No existing columns were dropped or altered. The 335 legacy rows remained intact through the migration; the seed script handled the wipe + reinsert as a separate step. This means the migration is independently reviewable and rollback-friendly (the reverse migration would just `DROP COLUMN` / `DROP TABLE` / restore the FK rule).

### `DEFAULT_COACH_ID` selection rationale

Of the 4 distinct user_ids found in `food_items.estimated`:
- `71a8c873…` — `275939731@telegram.fitpal.bot` (production)
- `ae521c1a…` — `275939731@dev.fitpal.bot` (dev)
- `fbeeb45f…` — `dev@dev.fitpal.bot` (Studio default)
- `72c10336…` — `e2e@test.fitpal.bot` (E2E test fixture)

Picked production because functionally any UUID works (system always reads/writes through the same constant) but production is safest from accidental cleanup during test infrastructure changes.

### Why kept legacy `name` column

If we removed `name` in Plan 1, `food_service.py` queries `FoodItem.name.ilike(...)` would AttributeError at the ORM layer — the bot would break instantly. Keeping `name` (populated via `name = name_en` during seed) lets the bot stay functional in English-only mode between Plan 1 and Plan 2. Plan 2 ships a follow-up migration that drops `name` after services migrate to `name_en`/`name_he`.
