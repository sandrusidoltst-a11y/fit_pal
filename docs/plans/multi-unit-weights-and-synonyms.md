# Feature: Multi-Unit Weights + Synonyms (replace `default_unit` / `default_unit_weight_g`)

The following plan should be complete, but it's important to validate documentation and codebase patterns and task sanity before implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files.

## Feature Description

Replace the single-unit-per-food schema (`FoodItem.default_unit` + `FoodItem.default_unit_weight_g`) with a multi-unit map (`FoodItem.unit_weights: dict[str, float]`) plus a coach-curated synonym map (`FoodItem.unit_synonyms: dict[str, str]`). Drop the 9-value `Literal` constraint on the `unit` field across schemas — the parser emits whatever unit the user said, verbatim, plus an LLM-estimated `amount_g` as a safety net. The resolver chain (`unit_weights` → `unit_synonyms` → parser's `amount_g` fallback) handles all matching, including multilingual, in one place. The static 8-bucket reference table in `prompts/input_parser.md` is dropped — the parser stops doing normalization, that job moves entirely into the coach-curated synonym map.

## User Story

As a FitPal user
I want to log foods using whatever natural unit comes to mind ("1 piece of chicken", "2 slices of pizza", "1 קערה אסאי") in any language
So that the bot computes correct macros without forcing me to convert to grams or remember the "official" unit name

## Problem Statement

The current design has a single canonical natural unit per food (`default_unit`) plus a single weight (`default_unit_weight_g`). When the user logs a unit that doesn't match the curated default — or when the food row has `default_unit_weight_g IS NULL` (common for self-healed estimated foods and any food the coach didn't curate) — `resolve_amount_g` (`src/services/food_service.py:31-47`) silently returns `count` as if it were grams. "1 piece of chicken" gets logged as 1 gram of chicken (~1.6 kcal) with no error, no warning. Confirmed via dev-bot smoke during PR #29 (commit `873791e`).

Three tightly coupled architectural issues underlie the bug:

1. **Single-unit schema** — pizza can be a "slice" or a "piece"; bread can be a "slice" or a "piece"; chicken can be a "piece" (whole breast) or "slice" (deli). One column doesn't fit.
2. **Parser-side normalization** — the `Literal[g, piece, slice, scoop, bottle, cup, tbsp, tsp, can]` constraint plus the static 28-food reference table in `prompts/input_parser.md` forces the parser to coerce the user's unit into a fixed enum. This duplicates the matching logic that the synonym layer already handles.
3. **No edit-side fallback** — the input parser has the LLM-estimated `amount_g` as a safety net when the resolver misses, but the edit flow (`confirmation_node._apply_edits`, `src/agents/nodes/confirmation_node.py:233-321`) doesn't. Edits to uncurated units silently fail or relocate the 1g bug.

## Solution Statement

Schema: replace `default_unit` + `default_unit_weight_g` with two JSONB columns on `FoodItem`:
- `unit_weights: dict[str, float]` — coach-curated map of canonical unit string → weight in grams (`{"slice": 110}`).
- `unit_synonyms: dict[str, str]` — coach-curated map of any-language alias → canonical key in `unit_weights` (`{"piece": "slice", "פרוסה": "slice"}`).

Schemas: drop the `Literal` constraint on `SingleFoodItem.unit` and `ItemEdit.new_unit` (free-form `str`). Add `amount_g: Optional[float]` on `SingleFoodItem` and `new_amount_g: Optional[float]` on `ItemEdit` — emitted by the LLM whenever `unit != "g"`.

Resolver: `resolve_amount_g(food, unit, count, llm_estimated_amount_g)` performs a 3-step lookup:
1. `unit in unit_weights` → `count * unit_weights[unit]`
2. `unit in unit_synonyms` → resolve to canonical key → `count * unit_weights[canonical]`
3. `llm_estimated_amount_g is not None` → use it as-is (already a total, not per-unit)
4. last-resort: log warning, return `count` (preserves current behavior so we never crash, only warn)

Prompts: rewrite `prompts/input_parser.md` (drop reference table, drop normalization), `prompts/confirmation_parser.md` (mirror new `ItemEdit` schema), `prompts/macro_estimation.md` (consume parser's `amount_g` as authoritative weight; estimate macros only).

Coach-curated only — no self-heal in v1. Off-menu estimation path consumes the parser's `amount_g` rather than re-estimating.

## Feature Metadata

**Feature Type**: Refactor (with embedded bug fix)
**Estimated Complexity**: High
**Primary Systems Affected**: `src/models.py`, `src/services/food_service.py`, `src/agents/nodes/{calculate_macros_node,confirmation_node,commit_node}.py`, `src/schemas/{input_schema,confirmation_schema,estimation_schema}.py`, `src/agents/state.py`, `prompts/{input_parser,confirmation_parser,macro_estimation}.md`, Supabase schema, seed scripts, all tests touching food/unit logic.
**Dependencies**: No new external libraries. `JSONB` column type is standard PostgreSQL/SQLAlchemy.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: READ BEFORE IMPLEMENTING

**Schema & data layer**
- `src/models.py:13-32` — `FoodItem` model. Lines 23-24 are the columns we're replacing.
- `src/services/food_service.py:31-47` — `resolve_amount_g` (the bug). Whole function rewritten.
- `src/services/food_service.py:60-88` — `compute_food_macros` returns dict including `default_unit` / `default_unit_weight_g` (lines 80-81). Replace with `unit_weights` / `unit_synonyms`.
- `src/services/food_service.py:179-232` — `create_food_item_record`. Signature uses old fields (188-189, 208-209). Update to new fields.
- `src/services/food_service.py:240-258` — `_serialize_food_candidate`. Already omits unit fields — no change needed but verify.
- `src/services/food_service.py:284-311` — `calculate_food_macros` tool. Signature gains `llm_estimated_amount_g: Optional[float]` and threads it into `resolve_amount_g`. Docstring (286-296) needs rewriting.
- `src/services/food_service.py:314-360` — `create_food_item` tool. Update signature to accept `unit_weights` / `unit_synonyms`.

**State & schemas**
- `src/agents/state.py:108-133` — `MacroResult` TypedDict. Lines 127-128 (`default_unit` / `default_unit_weight_g`) replaced; add `amount_g_estimated: Optional[float]` (parser's estimate, carried for edit-side fallback).
- `src/schemas/input_schema.py:16-30` — `SingleFoodItem`. Drop `Literal` on `unit` (line 22-27). Add `amount_g: Optional[float]`.
- `src/schemas/confirmation_schema.py:6-31` — `ItemEdit`. Drop `Literal` on `new_unit` (lines 22-31). Add `new_amount_g: Optional[float]`.
- `src/schemas/estimation_schema.py:6-56` — `MacroEstimation`. Remove `amount_g_estimated` (lines 9-18), `default_unit` (47-52), `default_unit_weight_g` (53-56). Estimation now consumes parser's `amount_g` and only estimates macros + name + category + tag.

**Graph nodes**
- `src/agents/nodes/calculate_macros_node.py:48-90` — DB path. Update `calculate_food_macros.ainvoke` call (50-52) to pass `llm_estimated_amount_g`. Update `MacroResult` construction (71-90) — drop `default_unit` / `default_unit_weight_g` (84-85), add `amount_g_estimated`.
- `src/agents/nodes/calculate_macros_node.py:91-115` — Estimation path. Update `_estimate_macros` call (99-101) to pass parser's `amount_g`.
- `src/agents/nodes/calculate_macros_node.py:118-158` — `_estimate_macros`. Pass `amount_g` from input. Update `MacroResult` return (139-158) — drop `default_unit` / `default_unit_weight_g` (152-153).
- `src/agents/nodes/confirmation_node.py:31-86` — `_format_batch_preview`. The current implementation (lines 64-73) uses `_unit_label_key` to look up i18n labels for `original_unit`. Keep this for *known* labels (the existing 8) but fall through to rendering `original_unit` verbatim when no i18n key matches. **Decision: keep the i18n table as a polish layer but never crash on unknown units.**
- `src/agents/nodes/confirmation_node.py:233-321` — `_apply_edits`. Lines 271-321 contain the DB / estimated split. Both branches need the new resolver: pass `llm_estimated_amount_g=edit.new_amount_g` into `calculate_food_macros.ainvoke` (DB branch, 273-279). Estimated branch (291-309) replaced — remove `default_unit_weight_g` mismatch error path; resolve via the same chain.
- `src/agents/nodes/commit_node.py:44-81` — `commit_node`. Lines 59-60 pass `default_unit` / `default_unit_weight_g` into `create_food_item.ainvoke`. Replace with `unit_weights` / `unit_synonyms`. For estimated foods we don't have synonyms — pass `unit_weights = {parser_unit: amount_g_per_unit}` derived from the user's stated unit and amount, or `{}` if we can't compute it cleanly. **Decision: estimated rows write `unit_weights={}` and `unit_synonyms={}` — coach can curate later if the food becomes popular. Keeps commit_node simple.**

**Prompts**
- `prompts/input_parser.md:1-80` — Section 2.7 (the static 28-food unit-bucket reference table) and Step 2 quantity/unit extraction (54-69) rewritten. Drop the `Literal` reference; instruct to emit user's word verbatim + estimated `amount_g`.
- `prompts/confirmation_parser.md` — read whole file. Update output schema description to match new `ItemEdit` shape (`new_unit` is free-form, `new_amount_g` is required when `new_unit != "g"`).
- `prompts/macro_estimation.md` — read whole file. Drop instructions about `amount_g_estimated` / `default_unit` / `default_unit_weight_g`. Estimator only emits macros + name + category + tag.

**Seed & migration data**
- `src/scripts/seed_canonical_catalog.py:60-130` — CSV ingestion writes `default_unit` (line 66, 110, 126) and `default_unit_weight_g` (67, 110, 127). Update to write `unit_weights` JSON. CSV format change: replace `default_unit,default_unit_weight_g` columns with `unit_weights` (JSON-encoded) and `unit_synonyms` (JSON-encoded).
- `data/canonical_food_catalog.csv` — gitignored. Coach maintains externally. Update column headers + transform existing rows: `{default_unit:"piece", default_unit_weight_g:130}` → `{unit_weights:'{"piece":130}', unit_synonyms:'{}'}`. **Action: produce a one-shot Python helper `src/scripts/migrate_csv_to_unit_weights.py` that converts the existing CSV in place (idempotent), so the coach doesn't have to hand-edit.**

**Tests touching old columns** (must update or delete in this PR)
- `tests/conftest.py:101-102` — fixture passes `default_unit="g", default_unit_weight_g=None`. Replace.
- `tests/unit/test_food_service_helpers.py:18-42` — direct `resolve_amount_g` tests using `MagicMock(default_unit=..., default_unit_weight_g=...)`. Full rewrite to test new resolver chain (weights hit, synonyms hit, fallback to estimate, last-resort).
- `tests/unit/test_calculate_macros_node.py:30-31, 48-49, 187-188, 275-276, 289-290, 334-335, 397-398` — many fixtures and assertions reference old fields. Update.
- `tests/unit/test_feedback_logic.py:33-34, 92-93` — fixture references. Update.
- Search for any other test references to the dropped fields before committing.

**Reference: prior commits to read for design context**
- `commit_logs/2026-04-18_22-33-24_feat-food-catalog-migration-plan-1.md` — original schema design rationale (single-unit was a v1 simplification).
- `commit_logs/2026-05-08_18-38-21_hitl-natural-units.md` — most recent natural-unit work; explains current `(count, unit)` plumbing through `MacroResult` and `_apply_edits`.

### New Files to Create

- `src/scripts/migrate_csv_to_unit_weights.py` — one-shot helper to convert existing `data/canonical_food_catalog.csv` columns (`default_unit`, `default_unit_weight_g`) into `unit_weights` JSON. Idempotent; safe to re-run.
- `tests/integration/test_food_service_unit_resolution.py` — new integration tests against real Supabase: curated direct hit, curated synonym hit, uncurated fallback, last-resort no-estimate path.

### Relevant Documentation YOU SHOULD READ BEFORE IMPLEMENTING

- [SQLAlchemy 2.x JSONB column type for PostgreSQL](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#sqlalchemy.dialects.postgresql.JSONB)
  - Section: Defining JSONB columns, default values, indexing
  - Why: We're adding two JSONB columns with `server_default="{}"`. Need to confirm correct import (`from sqlalchemy.dialects.postgresql import JSONB`) and that `Mapped[dict[str, float]]` works as expected.
- [Supabase Database Migrations docs](https://supabase.com/docs/guides/database/postgres/which-database-migrations-tool)
  - Section: SQL migrations via dashboard or CLI
  - Why: Schema migration process for adding columns + backfilling + dropping columns. We use Supabase migrations (not `Base.metadata.create_all()`), per `docs/patterns/schema-management.md`.
- [Pydantic v2 Optional fields with default None](https://docs.pydantic.dev/latest/concepts/fields/#field-defaults)
  - Section: Optional vs required fields
  - Why: `amount_g` and `new_amount_g` should be `Optional[float] = None` (truly optional — emitted only when `unit != "g"`). LLM with structured output may emit null when not applicable.

### Patterns to Follow

**Tool-First Service Layer** (from `docs/patterns/tool-first.md`):
- Pure helpers in `food_service.py` (no DB, no I/O) — `resolve_amount_g`, `compute_servings`, `compute_food_macros`. Add `resolve_amount_g(food, unit, count, llm_estimated_amount_g)` here.
- Service functions accept `session: AsyncSession` for DI/testability. `@tool` wrappers own their own session via `async with get_async_db_session() as session:`.
- Nodes never import DB sessions; they call `await tool.ainvoke({...})`.

**Async LangGraph Nodes** (from `docs/patterns/async-patterns.md`):
- All node functions are `async def`. All tool calls use `await tool.ainvoke({...})`.
- Never block the event loop with sync I/O.

**Schema Management** (from `docs/patterns/schema-management.md`):
- Production schema changes go through Supabase migrations (not SQLAlchemy `create_all`).
- Tests use `Base.metadata.create_all()` against `TEST_DATABASE_URL` (in-memory or test Postgres); see `tests/conftest.py`.
- Migration must include: ADD columns, BACKFILL data, DROP old columns — in order.

**Pydantic Output via `with_structured_output`** (from `docs/patterns/llm-config.md`):
- Never parse raw LLM strings. Use `llm.with_structured_output(Schema)`.
- Schemas live in `src/schemas/`. Treat the schema as the contract; add fields, regenerate prompt, test.

**i18n Pattern** (from `src/i18n/`):
- `MESSAGES` dict loaded based on `BOT_LANGUAGE` env var.
- Key naming: `confirmation_unit_label_<unit>_<singular|plural>`.
- For unknown unit strings, fall through to rendering the unit verbatim. Preview never crashes.

**Logging Pattern**:
- `import structlog` → `logger = structlog.get_logger(__name__)`.
- Structured fields: `logger.warning("resolve fallback", food=food.name_en, unit=unit, reason="no_curated_weight")`.

---

## IMPLEMENTATION PLAN

### Phase 1: Schema Foundation

Add the new columns alongside the old ones (additive, non-destructive). Backfill data. Code still reads old fields. This phase ships a working bot at every step.

**Tasks:**
- Supabase migration: ADD `unit_weights JSONB NOT NULL DEFAULT '{}'`, `unit_synonyms JSONB NOT NULL DEFAULT '{}'` to `food_items`.
- Backfill SQL: for every row where `default_unit IS NOT NULL AND default_unit_weight_g IS NOT NULL`, set `unit_weights = jsonb_build_object(default_unit, default_unit_weight_g)`. `unit_synonyms` stays `{}`.
- Update `src/models.py`: add the two new columns (keep old ones for now).

### Phase 2: Resolver + Service Layer

Rewrite `resolve_amount_g` to read the new columns. Update `calculate_food_macros` tool signature to accept and thread the parser's `amount_g`. Old columns still present in `FoodItem` but no longer read.

**Tasks:**
- Rewrite `resolve_amount_g(food, unit, count, llm_estimated_amount_g: Optional[float] = None)`.
- Update `compute_food_macros` to return `unit_weights` / `unit_synonyms` instead of `default_unit` / `default_unit_weight_g`.
- Update `calculate_food_macros` tool signature + docstring.
- Update `create_food_item_record` and `create_food_item` tool signatures: replace `default_unit` / `default_unit_weight_g` params with `unit_weights: Optional[dict] = None` / `unit_synonyms: Optional[dict] = None`.

### Phase 3: Schemas + Nodes

Drop `Literal` constraints. Add `amount_g` / `new_amount_g`. Update `MacroResult`. Update `calculate_macros_node`, `commit_node`, `confirmation_node._apply_edits` to use the new resolver chain.

**Tasks:**
- Update `SingleFoodItem`: drop `Literal` on `unit`, add `amount_g: Optional[float]`.
- Update `ItemEdit`: drop `Literal` on `new_unit`, add `new_amount_g: Optional[float]`.
- Update `MacroEstimation`: drop `amount_g_estimated`, `default_unit`, `default_unit_weight_g`.
- Update `MacroResult` TypedDict: drop `default_unit` / `default_unit_weight_g`, add `amount_g_estimated`.
- Update `calculate_macros_node`: thread `amount_g` from `current_item` into `calculate_food_macros.ainvoke`.
- Update `_estimate_macros`: pass `amount_g` from input parser as authoritative weight.
- Update `confirmation_node._apply_edits`: pass `new_amount_g` into `calculate_food_macros.ainvoke`. Estimated branch reuses the resolver chain — drop the `default_unit_weight_g` mismatch error path.
- Update `commit_node`: when creating estimated `FoodItem` rows, pass `unit_weights={}` and `unit_synonyms={}` (coach can curate later if needed).
- Update `_format_batch_preview` in `confirmation_node`: fall back to rendering `original_unit` verbatim when no i18n key matches (defensive `MESSAGES.get(...)` instead of `MESSAGES[...]`).

### Phase 4: Prompts

Rewrite the three prompts. The static reference table in `input_parser.md` goes away.

**Tasks:**
- `prompts/input_parser.md`: drop section 2.7 (unit-bucket reference table) and the maintenance note at line 1. Rewrite Step 2 quantity/unit extraction to: emit user's word verbatim (singular English form by convention when possible — soft instruction); when `unit != "g"`, also emit `amount_g` as best estimate of total weight in grams.
- `prompts/confirmation_parser.md`: update the output schema description for `new_unit` (free-form string) and `new_amount_g` (estimate of total grams). Add example covering an unrecognized-unit edit.
- `prompts/macro_estimation.md`: input now includes `amount_g`. Remove instructions to emit `amount_g_estimated`, `default_unit`, `default_unit_weight_g`. Estimator emits macros + name + category + tag only.

### Phase 5: Migration Cleanup

After all code paths use the new columns, drop the old columns. **Do NOT re-seed** — Phase 1's SQL backfill already preserved all existing curated unit data in `unit_weights`. Re-seeding would discard any catalog improvements made since the last seed.

**Tasks:**
- Update `seed_canonical_catalog.py` to read `unit_weights` and `unit_synonyms` columns from the new CSV format (for future fresh setups only — does NOT run as part of this PR).
- Update `src/scripts/migrate_csv_to_unit_weights.py` helper for the same reason (transforms the local CSV file format).
- Supabase migration: DROP `default_unit`, DROP `default_unit_weight_g`.
- `src/models.py`: remove the old columns.
- Search-and-clean: any remaining references to the old fields in source/tests.

**Excluded from this PR:**
- ❌ Wiping and re-seeding `food_items`. Existing rows keep their data via the Phase 1 backfill.
- ❌ Populating `unit_synonyms` for existing rows. Stays `{}`. Coach can curate iteratively via direct SQL `UPDATE food_items SET unit_synonyms = '{"piece": "slice"}'::jsonb WHERE name_en = 'pizza'` — no wipe needed.

### Phase 6: Testing & Validation

Update unit fixtures, write new resolver-chain unit tests, write new integration test, run graph-api E2E.

**Tasks:**
- Rewrite `tests/unit/test_food_service_helpers.py` to test the new 4-step resolver chain.
- Update `tests/conftest.py:101-102` and all unit-test fixtures (`test_calculate_macros_node.py`, `test_feedback_logic.py`).
- Create `tests/integration/test_food_service_unit_resolution.py`: real-DB tests for all 4 resolver branches.
- Run full validation suite (lint + unit + integration + graph-api).
- Manual smoke via dev bot: log "1 piece of chicken" (was the original bug → should now resolve correctly).

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### Phase 1: Schema Foundation

#### 1.1 CREATE Supabase migration: add `unit_weights` and `unit_synonyms` columns

- **IMPLEMENT**: Via Supabase MCP server (`mcp__supabase__*`) or Supabase dashboard SQL editor:
  ```sql
  ALTER TABLE food_items
    ADD COLUMN unit_weights  JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN unit_synonyms JSONB NOT NULL DEFAULT '{}'::jsonb;

  -- Backfill existing rows that had a single curated unit
  UPDATE food_items
  SET unit_weights = jsonb_build_object(default_unit, default_unit_weight_g)
  WHERE default_unit IS NOT NULL
    AND default_unit_weight_g IS NOT NULL
    AND unit_weights = '{}'::jsonb;
  ```
- **PATTERN**: Mirrors the additive migration approach from `commit_logs/2026-04-18_22-33-24_feat-food-catalog-migration-plan-1.md` (Plan 1 was also additive — extend, don't drop).
- **GOTCHA**: Run the backfill in the SAME migration as the ADD COLUMN. If backfill is a separate step, code that lands in between will see `unit_weights = {}` and break.
- **GOTCHA**: Do NOT drop the old columns yet. Phase 5 drops them after all code paths are migrated.
- **VALIDATE**:
  ```sql
  SELECT
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE unit_weights != '{}'::jsonb) AS backfilled,
    COUNT(*) FILTER (WHERE default_unit IS NOT NULL AND default_unit_weight_g IS NOT NULL) AS expected
  FROM food_items;
  -- expect: backfilled == expected
  ```

#### 1.2 UPDATE `src/models.py` — add new columns to `FoodItem`

- **IMPLEMENT**: Add two new mapped columns alongside the existing ones (keep old):
  ```python
  from sqlalchemy.dialects.postgresql import JSONB
  # ...
  unit_weights:  Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
  unit_synonyms: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
  ```
- **PATTERN**: `src/models.py:13-32` for column declaration style. Use `Mapped[dict]` (SQLAlchemy 2.x typing); the JSONB column accepts any dict shape.
- **IMPORTS**: `from sqlalchemy.dialects.postgresql import JSONB` (add to existing sqlalchemy import line).
- **GOTCHA**: `Mapped[dict[str, float]]` vs `Mapped[dict[str, str]]` typing — SQLAlchemy doesn't enforce at the ORM layer; use `Mapped[dict]` or `Mapped[dict[str, Any]]` to keep things simple.
- **VALIDATE**: `uv run python -c "from src.models import FoodItem; print(FoodItem.__table__.c.unit_weights.type, FoodItem.__table__.c.unit_synonyms.type)"` — should print `JSONB JSONB`.

### Phase 2: Resolver + Service Layer

#### 2.1 REFACTOR `src/services/food_service.py:31-47` — rewrite `resolve_amount_g`

- **IMPLEMENT**:
  ```python
  def resolve_amount_g(
      food: FoodItem,
      unit: str,
      count: float,
      llm_estimated_amount_g: Optional[float] = None,
  ) -> float:
      """Convert (unit, count) to grams via the multi-unit resolver chain.

      Order:
          1. unit == "g"            → count
          2. unit in unit_weights   → count * unit_weights[unit]
          3. unit in unit_synonyms  → count * unit_weights[unit_synonyms[unit]]
          4. llm_estimated_amount_g → use as-is (already a total)
          5. last-resort fallback   → count (with warning log)
      """
      if unit == "g":
          return count

      weights = food.unit_weights or {}
      if unit in weights:
          return count * weights[unit]

      synonyms = food.unit_synonyms or {}
      if unit in synonyms:
          canonical = synonyms[unit]
          if canonical in weights:
              return count * weights[canonical]
          logger.warning(
              "synonym points to missing key",
              food=food.name_en, unit=unit, canonical=canonical,
          )

      if llm_estimated_amount_g is not None:
          return llm_estimated_amount_g

      logger.warning(
          "resolve_amount_g last-resort fallback",
          food=food.name_en, unit=unit, count=count,
      )
      return count
  ```
- **PATTERN**: Pure helper — no DB, no I/O. Lives in the "Pure helpers" section above the service functions (after line 28 marker comment).
- **IMPORTS**: No new imports — `logger` already exists at line 24.
- **GOTCHA**: `food.unit_weights or {}` — defensive against any row that somehow has NULL (shouldn't happen given `NOT NULL DEFAULT '{}'`, but the migration could leave gaps if it's mid-rollout).
- **GOTCHA**: Synonym integrity (`canonical in weights`) — log a warning but still fall through to `llm_estimated_amount_g`. Don't silently use a wrong weight.
- **VALIDATE**: `uv run pytest tests/unit/test_food_service_helpers.py -v` (will fail until 6.1 rewrites the tests; that's expected — re-run after 6.1).

#### 2.2 UPDATE `src/services/food_service.py:60-88` — `compute_food_macros`

- **IMPLEMENT**: In the returned dict (lines 70-88), replace:
  ```python
  "default_unit": food.default_unit,
  "default_unit_weight_g": food.default_unit_weight_g,
  ```
  with:
  ```python
  "unit_weights": food.unit_weights,
  "unit_synonyms": food.unit_synonyms,
  ```
- **PATTERN**: Pure dict construction — same shape as before, just different keys.
- **GOTCHA**: Downstream consumers in `calculate_macros_node.py:84-85` will need matching updates in 3.5.
- **VALIDATE**: `uv run python -c "from src.services.food_service import compute_food_macros; help(compute_food_macros)"` — sanity check.

#### 2.3 UPDATE `src/services/food_service.py:284-311` — `calculate_food_macros` tool

- **IMPLEMENT**: Change tool signature to:
  ```python
  @tool
  async def calculate_food_macros(
      food_id: str,
      count: float,
      unit: str = "g",
      llm_estimated_amount_g: Optional[float] = None,
  ) -> dict:
  ```
  Inside (line 304), pass through:
  ```python
  amount_g = resolve_amount_g(food, unit, count, llm_estimated_amount_g)
  ```
  Update docstring (lines 286-296): remove "Unit mismatch" language; describe the new fallback chain.
- **PATTERN**: `@tool` wrappers own their session via `async with get_async_db_session()`. Pattern from `food_service.py:260-281` (`search_food`).
- **GOTCHA**: `resolve_amount_g` no longer raises `ValueError`. Remove the `try/except ValueError` block at lines 303-310. The tool always returns a dict (no error case from unit resolution).
- **VALIDATE**: `uv run python -c "from src.services.food_service import calculate_food_macros; print(calculate_food_macros.args_schema.model_json_schema())"` — confirm new arg appears.

#### 2.4 UPDATE `src/services/food_service.py:179-232` — `create_food_item_record`

- **IMPLEMENT**: Replace these two parameters in the signature:
  ```python
  default_unit: Optional[str] = None,
  default_unit_weight_g: Optional[float] = None,
  ```
  with:
  ```python
  unit_weights: Optional[dict] = None,
  unit_synonyms: Optional[dict] = None,
  ```
  Update the `FoodItem(...)` instantiation (lines 201-212) accordingly:
  ```python
  unit_weights=unit_weights or {},
  unit_synonyms=unit_synonyms or {},
  ```
- **PATTERN**: Service function with explicit session, called by the `@tool` wrapper below.
- **VALIDATE**: `uv run python -c "import inspect; from src.services.food_service import create_food_item_record; print(inspect.signature(create_food_item_record))"`.

#### 2.5 UPDATE `src/services/food_service.py:314-360` — `create_food_item` tool

- **IMPLEMENT**: Mirror 2.4 — replace `default_unit` / `default_unit_weight_g` parameters with `unit_weights` / `unit_synonyms`. Pass through to `create_food_item_record`.
- **VALIDATE**: `uv run python -c "from src.services.food_service import create_food_item; print(create_food_item.args_schema.model_json_schema())"`.

### Phase 3: Schemas + Nodes

#### 3.1 UPDATE `src/schemas/input_schema.py:16-30` — `SingleFoodItem`

- **IMPLEMENT**:
  ```python
  class SingleFoodItem(BaseModel):
      food_name: str = Field(..., description="Normalized name for DB lookup")
      count: float = Field(..., description="Numeric quantity in the given unit (e.g., 2 for '2 eggs', 200 for '200g chicken')")
      unit: str = Field(
          default="g",
          description=(
              "Unit of measurement, verbatim from user input. 'g' for grams; "
              "any natural unit otherwise (piece, slice, bowl, wedge, etc.). "
              "No fixed enum — emit what the user said in singular English form when possible."
          ),
      )
      amount_g: Optional[float] = Field(
          default=None,
          description=(
              "Required when unit != 'g'. Your best estimate of the TOTAL gram "
              "weight for the user's stated quantity (count × per-unit weight). "
              "Acts as the resolver's safety net when the food's curated unit_weights "
              "doesn't contain this unit."
          ),
      )
      original_text: str = Field(..., description="The original text description of the food item")
  ```
- **GOTCHA**: `amount_g` is `Optional[float] = None` — Pydantic v2 with `Optional[X] = None` is correctly treated as optional in OpenAI strict structured output.
- **VALIDATE**: `uv run python -c "from src.schemas.input_schema import SingleFoodItem; print(SingleFoodItem.model_json_schema())"` — confirm `unit` is a free-form string, `amount_g` is optional float.

#### 3.2 UPDATE `src/schemas/confirmation_schema.py:6-31` — `ItemEdit`

- **IMPLEMENT**:
  ```python
  class ItemEdit(BaseModel):
      item_index: int = Field(..., description="0-based index of the item in the batch to edit")
      edit_type: Literal["change_amount", "remove"] = Field(..., description="Type of edit")
      new_count: Optional[float] = Field(None, description="New quantity in the unit specified by new_unit (only for change_amount)")
      new_unit: Optional[str] = Field(
          None,
          description=(
              "Unit for new_count, verbatim from user input (only for change_amount). "
              "'g' for grams; any natural unit otherwise. If the user gave only a count "
              "without a unit, inherit from the item's original_unit shown in the batch context."
          ),
      )
      new_amount_g: Optional[float] = Field(
          None,
          description=(
              "Required when new_unit != 'g'. Your best estimate of the TOTAL gram weight "
              "for the user's edited quantity. Acts as the resolver's safety net."
          ),
      )
  ```
- **VALIDATE**: `uv run python -c "from src.schemas.confirmation_schema import ItemEdit; print(ItemEdit.model_json_schema())"`.

#### 3.3 UPDATE `src/schemas/estimation_schema.py:6-56` — `MacroEstimation`

- **IMPLEMENT**: Remove `amount_g_estimated` (lines 9-18), `default_unit` (47-52), `default_unit_weight_g` (53-56). Final schema:
  ```python
  class MacroEstimation(BaseModel):
      """Macro estimation for off-menu foods. Weight is supplied by the input parser
      via SingleFoodItem.amount_g — this schema only estimates the per-amount macros."""

      calories: float = Field(..., description="Estimated calories (kcal) for the given amount in grams")
      protein: float = Field(..., description="Estimated protein in grams for the given amount")
      carbs: float = Field(..., description="Estimated carbohydrates in grams for the given amount")
      fat: float = Field(..., description="Estimated fat in grams for the given amount")
      name_en: str = Field(..., description="English name of the food (translate if needed)")
      name_he: str = Field(..., description="Hebrew name of the food (translate if needed)")
      category: Optional[Literal["protein", "carb", "fat", "free", "free_calories", "forbidden_main"]] = Field(default=None, description="Coach-method category. Null if uncertain.")
      tag: Optional[Literal["lean", "medium", "fatty"]] = Field(default=None, description="Optional protein tag. Null if not a protein or uncertain.")
  ```
- **VALIDATE**: `uv run python -c "from src.schemas.estimation_schema import MacroEstimation; print(list(MacroEstimation.model_fields.keys()))"`.

#### 3.4 UPDATE `src/agents/state.py:108-133` — `MacroResult`

- **IMPLEMENT**: Drop `default_unit` (line 127), `default_unit_weight_g` (line 128). Add:
  ```python
  amount_g_estimated: Optional[float]   # Parser's LLM estimate, carried for edit-side fallback
  ```
- **GOTCHA**: TypedDict — fields are positional in some readers but order doesn't matter for runtime. Place `amount_g_estimated` near `amount_g` for readability.

#### 3.5 UPDATE `src/agents/nodes/calculate_macros_node.py:48-115` — DB and estimation paths

- **IMPLEMENT**: 
  - DB path (lines 50-52): pass through the parser's estimate:
    ```python
    macros = await calculate_food_macros.ainvoke(
        {
            "food_id": selected_food_id,
            "count": count,
            "unit": unit,
            "llm_estimated_amount_g": current_item.get("amount_g"),
        }
    )
    ```
  - `MacroResult` construction (lines 71-90): replace `default_unit` / `default_unit_weight_g` (lines 84-85) with:
    ```python
    "amount_g_estimated": current_item.get("amount_g"),
    ```
    (Note: also remove the `unit_weights` / `unit_synonyms` fields from `MacroResult` if they were added by mistake — only `amount_g_estimated` lives on `MacroResult`. The new schema columns are read by the resolver, not carried in state.)
  - Estimation path (lines 99-101): `_estimate_macros` no longer estimates weight — it consumes the parser's estimate:
    ```python
    macro_result = await _estimate_macros(
        food_name=food_name,
        count=count,
        unit=unit,
        amount_g=current_item.get("amount_g"),
        original_text=current_item.get("original_text", ""),
    )
    ```
- **VALIDATE**: `uv run pytest tests/unit/test_calculate_macros_node.py -v` (will fail until 6.x updates fixtures; expected).

#### 3.6 UPDATE `src/agents/nodes/calculate_macros_node.py:118-158` — `_estimate_macros`

- **IMPLEMENT**: New signature:
  ```python
  async def _estimate_macros(
      food_name: str,
      count: float,
      unit: str,
      amount_g: Optional[float],
      original_text: str,
  ) -> MacroResult:
      llm = get_llm_for_node("estimation_node")
      structured_llm = llm.with_structured_output(MacroEstimation)

      # Determine the gram total: if parser gave one, use it; else count is grams.
      resolved_amount_g = amount_g if amount_g is not None else count

      messages = [
          SystemMessage(content=_ESTIMATION_PROMPT),
          HumanMessage(
              content=(
                  f"Estimate macros for: {food_name}, "
                  f"quantity: {count} {unit} (= {resolved_amount_g}g)"
              )
          ),
      ]
      result = await structured_llm.ainvoke(messages)

      return {
          "name_en": result.name_en,
          "name_he": result.name_he,
          "amount_g": resolved_amount_g,
          "calories": round(result.calories, 1),
          "protein": round(result.protein, 1),
          "carbs": round(result.carbs, 1),
          "fat": round(result.fat, 1),
          "source": "estimated",
          "category": result.category,
          "tag": result.tag,
          "serving_amount_g": None,
          "servings": None,
          "amount_g_estimated": amount_g,
          "original_text": original_text,
          "food_id": None,
          "original_count": count,
          "original_unit": unit,
      }
  ```
- **GOTCHA**: When `amount_g is None` AND `unit != "g"`, parser failed to emit estimate. Two options: (a) fall back to `count` as grams (current behavior, but will under-estimate), or (b) raise. Choose (a) — matches the resolver's last-resort behavior; log a warning.

#### 3.7 UPDATE `src/agents/nodes/confirmation_node.py:233-321` — `_apply_edits`

- **IMPLEMENT**:
  - DB branch (lines 271-290): pass `llm_estimated_amount_g`:
    ```python
    macros = await calculate_food_macros.ainvoke(
        {
            "food_id": item["food_id"],
            "count": edit.new_count,
            "unit": edit.new_unit,
            "llm_estimated_amount_g": edit.new_amount_g,
        }
    )
    ```
  - Estimated branch (lines 291-321): replace the `default_unit_weight_g` mismatch error path with the same resolver. Since estimated foods don't have a `food_id` to look up via `calculate_food_macros`, but the `MacroResult` carries `amount_g_estimated` (parser's original estimate) plus the new edit's `new_amount_g`, derive new grams:
    ```python
    if edit.new_unit == "g":
        new_grams = edit.new_count
    elif edit.new_amount_g is not None:
        new_grams = edit.new_amount_g
    elif edit.new_unit == item.get("original_unit") and item["original_count"] > 0:
        # Same unit as original — scale proportionally from the original amount
        new_grams = (item["amount_g"] / item["original_count"]) * edit.new_count
    else:
        edit_errors.append(_surface_edit_error(item, edit, "Could not resolve unit for estimated item"))
        continue
    ```
    Then scale macros proportionally as before (lines 311-319).
- **GOTCHA**: This branch is the only place we still have proportional scaling logic — for estimated items where the LLM didn't emit `new_amount_g`. Acceptable: estimated items are rarer and this is a bounded fallback.

#### 3.8 UPDATE `src/agents/nodes/confirmation_node.py:31-86` — `_format_batch_preview` defensive i18n

- **IMPLEMENT**: At line 67-68, change:
  ```python
  label = MESSAGES[_unit_label_key(item["original_unit"], item["original_count"])]
  ```
  to:
  ```python
  label = MESSAGES.get(
      _unit_label_key(item["original_unit"], item["original_count"]),
      item["original_unit"],   # fall back to raw unit string when no i18n entry
  )
  ```
- **PATTERN**: Defensive i18n lookup so unknown units render gracefully.
- **VALIDATE**: Manually trace by reading the diff — no test covers the unknown-unit branch yet (see 6.x).

#### 3.9 UPDATE `src/agents/nodes/commit_node.py:44-81` — `commit_node`

- **IMPLEMENT**: Replace lines 59-60 (`"default_unit": item.get("default_unit"), "default_unit_weight_g": item.get("default_unit_weight_g"),`) with:
  ```python
  "unit_weights": {},
  "unit_synonyms": {},
  ```
- **GOTCHA**: V1 design decision: estimated foods get empty maps. Coach can curate later when a food gets popular. Don't try to derive unit_weights from the parser's amount_g here — the per-unit weight semantics are too fragile to write automatically (count=2 / amount_g=260 → "piece"=130, but only if user said "2 pieces" not "2 slices"). Coach-curated only is the cleanest invariant.

### Phase 4: Prompts

#### 4.1 REWRITE `prompts/input_parser.md` quantity/unit section

- **IMPLEMENT**: 
  - Remove the maintenance note at line 1.
  - Remove section 2.7 entirely (the static 28-food unit-bucket table — find the section by reading the file).
  - Rewrite Step 2 quantity/unit extraction (lines 56-69) to:
    ```markdown
    2. **Quantity & Unit Extraction**:
       - Extract `count` (numeric quantity) and `unit` (verbatim from user input) for each food item.
       - `unit` is FREE-FORM — emit whatever word the user used (piece, slice, bowl, wedge, scoop, חתיכה, פרוסה, etc.). Prefer singular English form when the user's word has an obvious English equivalent ("חתיכה" → "piece"); otherwise emit the user's word as-is.
       - When the user said grams (or no unit at all and the food is gram-native — rice, oats, pasta), emit `unit="g"` and put the gram amount in `count`.
       - **When `unit != "g"`, you MUST also emit `amount_g`**: your best estimate of the TOTAL gram weight for the stated quantity (count × per-unit weight). For "2 eggs" emit `amount_g≈100`; for "1 piece of chicken" emit `amount_g≈130`; for "1 bowl of açaí" emit `amount_g≈350`.
       - Examples:
         - "200g chicken" → `{count: 200, unit: "g", amount_g: null}`
         - "2 eggs" → `{count: 2, unit: "piece", amount_g: 100}`
         - "1 slice of bread" → `{count: 1, unit: "slice", amount_g: 30}`
         - "1 cup rice" → `{count: 1, unit: "cup", amount_g: 158}`
         - "1 bowl of açaí" → `{count: 1, unit: "bowl", amount_g: 350}`
         - "חתיכת פיצה" → `{count: 1, unit: "piece", amount_g: 110}`
    ```
  - Preserve sections on Hebrew word-form quantifiers (lines 71+) — those are still valid.
- **GOTCHA**: Do NOT specify any closed enum for `unit`. The schema is now `str`.

#### 4.2 UPDATE `prompts/confirmation_parser.md`

- **IMPLEMENT**: Read the file first. Update the `ItemEdit` output description to match 3.2:
  - `new_unit`: free-form string (no fixed enum). Inherit from `original_unit` on count-only edits.
  - `new_amount_g`: REQUIRED when `new_unit != "g"`. Best estimate of the total grams for the new quantity.
  - Add an example showing an unrecognized-unit edit (e.g., user says "make it 1 wedge" on a pizza item).

#### 4.3 UPDATE `prompts/macro_estimation.md`

- **IMPLEMENT**: Read the file first. Remove all instructions about emitting `amount_g_estimated`, `default_unit`, `default_unit_weight_g`. The estimator now receives the gram amount as part of the input (e.g., "Estimate macros for: pizza, quantity: 2 slice (= 220g)") and emits ONLY: `calories, protein, carbs, fat, name_en, name_he, category, tag`.

### Phase 5: Migration Cleanup + Seed Script

#### 5.1 CREATE `src/scripts/migrate_csv_to_unit_weights.py`

- **IMPLEMENT**: One-shot helper to convert `data/canonical_food_catalog.csv` columns. Reads the CSV, transforms each row:
  ```python
  # Old columns: default_unit, default_unit_weight_g
  # New columns: unit_weights (JSON string), unit_synonyms (JSON string, default "{}")
  if row["default_unit"] and row["default_unit_weight_g"]:
      row["unit_weights"] = json.dumps({row["default_unit"]: float(row["default_unit_weight_g"])})
  else:
      row["unit_weights"] = "{}"
  row["unit_synonyms"] = "{}"
  # Drop old columns
  ```
  Idempotent: if `unit_weights` column already exists with non-empty values, skip.
- **PATTERN**: `src/scripts/seed_canonical_catalog.py` for CSV-handling style.
- **VALIDATE**: Run on a copy of the CSV first. Diff to confirm sane transformation.

#### 5.2 UPDATE `src/scripts/seed_canonical_catalog.py:60-130`

- **IMPLEMENT**: 
  - Replace lines 66-67 (reading `default_unit` / `default_unit_weight_g`) with reading `unit_weights` / `unit_synonyms` as JSON-decoded dicts.
  - Update the SQL INSERT (lines 110, 114) to use the new column names.
  - Update the parameter dict (lines 126-127) accordingly.
- **GOTCHA**: The CSV stores JSON as strings — use `json.loads(row["unit_weights"])` before passing to the DB. When passing to SQLAlchemy `text()` with `:unit_weights`, ensure the type binds as JSONB (use `bindparam("unit_weights", type_=JSONB)` or pass the dict directly — asyncpg handles dict→JSONB automatically; sync psycopg2 may need `json.dumps`).

#### 5.3 SKIPPED — DO NOT RE-SEED

The original plan called for re-seeding here. **Removed**: existing curated data is preserved by Phase 1.1's SQL backfill. Re-seeding (`DELETE FROM food_items WHERE source = 'database'` + re-insert from CSV) would discard any catalog improvements made since the last seed.

If a fresh setup is ever needed (new dev DB, recovery), use the updated seed script (5.2) at that time. Not part of this PR.

**VALIDATE current data is intact** (read-only check, no mutations):
```sql
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE unit_weights != '{}'::jsonb) AS with_curated_units,
  COUNT(*) FILTER (WHERE jsonb_typeof(unit_weights) = 'object') AS valid_jsonb
FROM food_items WHERE source = 'database';
-- with_curated_units should match the count of rows that had a default_unit set pre-migration
```

#### 5.4 CREATE Supabase migration: drop old columns

- **IMPLEMENT**:
  ```sql
  ALTER TABLE food_items
    DROP COLUMN default_unit,
    DROP COLUMN default_unit_weight_g;
  ```
- **GOTCHA**: Verify NO code paths still read the old columns first. Run `grep -r "default_unit" src/ tests/ bot/` and confirm zero hits before applying.

#### 5.5 UPDATE `src/models.py` — remove old columns

- **IMPLEMENT**: Delete lines 23-24 (`default_unit`, `default_unit_weight_g`).
- **VALIDATE**: `uv run python -c "from src.models import FoodItem; assert not hasattr(FoodItem, 'default_unit'), 'still there'"`.

#### 5.6 SEARCH-AND-CLEAN remaining references

- **IMPLEMENT**: 
  ```bash
  grep -rn "default_unit\|default_unit_weight_g" src/ tests/ bot/ prompts/
  ```
  Triage: every hit is either (a) a comment to update, (b) a test fixture to update (covered in 6.x), or (c) a missed code path. Should be (b) only by this point.
- **VALIDATE**: After cleanup, the grep should only return matches in `commit_logs/` (historical, leave as-is) and `docs/plans/` (this plan + previous Plan 1 doc, leave as-is).

### Phase 6: Testing & Validation

#### 6.1 REWRITE `tests/unit/test_food_service_helpers.py`

- **IMPLEMENT**: New test class `TestResolveAmountG` covering:
  ```python
  def test_grams_passthrough(self):
      food = MagicMock(unit_weights={}, unit_synonyms={}, name_en="Rice")
      assert resolve_amount_g(food, "g", 180.0) == 180.0

  def test_unit_weights_direct_hit(self):
      food = MagicMock(unit_weights={"piece": 50.0}, unit_synonyms={}, name_en="Egg")
      assert resolve_amount_g(food, "piece", 2.0) == 100.0

  def test_unit_synonyms_resolution(self):
      food = MagicMock(unit_weights={"slice": 110.0}, unit_synonyms={"piece": "slice"}, name_en="Pizza")
      assert resolve_amount_g(food, "piece", 2.0) == 220.0

  def test_synonym_pointing_to_missing_key_falls_through(self, caplog):
      food = MagicMock(unit_weights={}, unit_synonyms={"piece": "slice"}, name_en="Broken")
      assert resolve_amount_g(food, "piece", 2.0, llm_estimated_amount_g=200.0) == 200.0

  def test_falls_back_to_llm_estimate(self):
      food = MagicMock(unit_weights={}, unit_synonyms={}, name_en="Mystery")
      assert resolve_amount_g(food, "bowl", 1.0, llm_estimated_amount_g=350.0) == 350.0

  def test_last_resort_returns_count_when_no_estimate(self):
      food = MagicMock(unit_weights={}, unit_synonyms={}, name_en="Mystery")
      assert resolve_amount_g(food, "bowl", 1.0) == 1.0  # warns, returns count
  ```
- **PATTERN**: Existing test file structure (`tests/unit/test_food_service_helpers.py:18-42`) — pytest classes, MagicMock for FoodItem.
- **VALIDATE**: `uv run pytest tests/unit/test_food_service_helpers.py -v` — all six pass.

#### 6.2 UPDATE `tests/conftest.py:101-102` and unit-test fixtures

- **IMPLEMENT**: 
  - `tests/conftest.py:101-102`: replace `default_unit="g", default_unit_weight_g=None` with `unit_weights={}, unit_synonyms={}`.
  - `tests/unit/test_calculate_macros_node.py`: lines 30-31, 48-49, 187-188, 275-276, 289-290, 334-335, 397-398 — all old-field references. Replace with new fields. The MagicMock-based fixtures need `unit_weights`/`unit_synonyms` attributes.
  - `tests/unit/test_feedback_logic.py`: lines 33-34, 92-93 — same treatment.
- **GOTCHA**: Tests that explicitly assert the OLD shape of `MacroResult` (e.g., `assert result["default_unit"] == "slice"`) need to be replaced with the new contract (e.g., `assert result["amount_g_estimated"] == 100.0`).
- **VALIDATE**: `uv run pytest tests/unit/ -v`. Should be green after this task.

#### 6.3 CREATE `tests/integration/test_food_service_unit_resolution.py`

- **IMPLEMENT**: Real-DB tests against the test Supabase. Each test creates a `FoodItem` row, then exercises the resolver via `calculate_food_macros.ainvoke`.
  ```python
  @pytest.mark.asyncio
  async def test_curated_direct_hit(test_session):
      food = await create_food_item_record(
          session=test_session,
          name_en="Pizza",
          name_he="פיצה",
          calories_per_100g=266.0,
          protein_per_100g=11.0,
          carbs_per_100g=33.0,
          fat_per_100g=10.0,
          unit_weights={"slice": 110.0},
          unit_synonyms={},
          user_id=str(uuid.uuid4()),
      )
      result = await calculate_food_macros.ainvoke({
          "food_id": str(food[0].id), "count": 2, "unit": "slice",
      })
      assert result["amount_g"] == 220.0

  @pytest.mark.asyncio
  async def test_synonym_hit(test_session):
      # ... unit_weights={"slice": 110}, unit_synonyms={"piece": "slice"}
      # query with unit="piece" → 110g
      ...

  @pytest.mark.asyncio
  async def test_uncurated_falls_back_to_estimate(test_session):
      # unit_weights={}, unit_synonyms={}
      # query with unit="bowl", llm_estimated_amount_g=350 → 350g
      ...

  @pytest.mark.asyncio
  async def test_uncurated_no_estimate_returns_count(test_session):
      # unit_weights={}, unit_synonyms={}
      # query with unit="bowl" (no estimate) → returns count, logs warning
      ...
  ```
- **PATTERN**: Existing integration tests in `tests/integration/` for service/tool patterns. Follow `test_food_service.py` conventions if it exists.
- **VALIDATE**: `uv run pytest tests/integration/test_food_service_unit_resolution.py -v`.

#### 6.4 RUN graph-API E2E suite

- **IMPLEMENT**: `uv run pytest tests/graph_api/ -v -s` — full server boot + curated/uncurated scenarios end-to-end.
- **GOTCHA**: graph_api tests need the server running; conftest auto-starts it. If a test fails with `BlockingError`, check `tests/graph_api/logs/server.log` (per memory note).

#### 6.5 MANUAL smoke test via dev bot

- **IMPLEMENT**: With `POLLING_MODE=true uv run python -m bot.gateway`, send the original-bug message to the bot:
  - "1 piece of chicken" — should now resolve to ~130g (parser estimate or curated weight, depending on row).
  - "1 bowl of açaí" — uncurated, should fall back to parser estimate.
  - "2 slices of pizza" — should hit `unit_weights["slice"]` if curated.
  - Edit a confirmed item: "actually 3 slices" — should re-resolve correctly.
  - Hebrew: "חתיכת פיצה" — should resolve via synonym (if curated) or fallback.
- **VALIDATE**: Confirm in Supabase `daily_logs` table that `amount_g` matches expectation for each scenario.

---

## TESTING STRATEGY

### Unit Tests

- New: `TestResolveAmountG` covering all 5 branches of the resolver chain (grams, weights, synonyms, fallback, last-resort).
- Updated: `test_calculate_macros_node.py` — both DB and estimation paths return new `MacroResult` shape with `amount_g_estimated` populated.
- Updated: `test_feedback_logic.py` — fixtures use new field names.
- Mock boundary: per `.claude/skills/test-engineering/SKILL.md` — mock the LLM and the DB at the service boundary; do NOT mock pure helpers.

### Integration Tests

- New: `tests/integration/test_food_service_unit_resolution.py` — real Supabase. Each branch of the resolver chain.
- Existing: `tests/integration/` suite re-run end-to-end to confirm no regressions.

### Graph-API Tests

- Existing graph-api E2E tests run against full langgraph server. Verify no regressions in confirmed flows (food logging, multi-item, query, chitchat).

### Edge Cases

- Synonym pointing to a non-existent canonical key (data integrity bug): logged warning, falls through to LLM estimate.
- Fractional counts: "0.5 slices of pizza" → `0.5 * 110 = 55g`.
- Hebrew unit string: "פרוסה" — resolves via `unit_synonyms` if coach curated, else falls back to parser's `amount_g`.
- Edit on uncurated unit (the cup-of-pizza story): `new_amount_g` from confirmation parser saves it.
- Edit on estimated item with same unit as original: proportional scaling from `amount_g / original_count`.
- Parser fails to emit `amount_g` when `unit != "g"`: last-resort fallback returns `count` and logs a warning.
- HITL preview with unknown unit string: falls back to rendering verbatim instead of crashing on missing i18n key.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

```bash
uv run ruff check src/ bot/ tests/
```

### Level 2: Unit Tests

```bash
uv run pytest tests/unit/ -v
```

### Level 3: Integration Tests

```bash
uv run pytest tests/integration/ -v
```

### Level 4: Graph-API E2E

```bash
uv run pytest tests/graph_api/ -v -s
```

### Level 5: Manual Smoke (dev bot)

```bash
POLLING_MODE=true uv run python -m bot.gateway
# Then send via Telegram:
# - "1 piece of chicken"
# - "1 bowl of açaí"
# - "2 slices of pizza" + edit "actually 3 slices"
# - "חתיכת פיצה"
# Verify Supabase daily_logs.amount_g for each.
```

### Level 6: Schema Sanity

```sql
-- Run in Supabase SQL editor
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE unit_weights != '{}'::jsonb) AS curated,
  COUNT(*) FILTER (WHERE unit_synonyms != '{}'::jsonb) AS with_synonyms,
  COUNT(*) FILTER (WHERE jsonb_typeof(unit_weights) != 'object') AS bad_weights,
  COUNT(*) FILTER (WHERE jsonb_typeof(unit_synonyms) != 'object') AS bad_synonyms
FROM food_items;
-- bad_* should be 0; curated should match the seed catalog
```

---

## ACCEPTANCE CRITERIA

- [ ] Schema: `food_items` has `unit_weights JSONB NOT NULL DEFAULT '{}'` and `unit_synonyms JSONB NOT NULL DEFAULT '{}'`. Old columns dropped.
- [ ] `resolve_amount_g` follows the documented 5-step chain (grams → weights → synonyms → llm estimate → last-resort).
- [ ] `SingleFoodItem.unit` and `ItemEdit.new_unit` are free-form `str` (no Literal).
- [ ] `SingleFoodItem.amount_g` and `ItemEdit.new_amount_g` are `Optional[float]`, populated by parser when `unit != "g"`.
- [ ] `MacroEstimation` no longer emits `amount_g_estimated` / `default_unit` / `default_unit_weight_g`.
- [ ] `prompts/input_parser.md` no longer contains the static 28-food unit-bucket table.
- [ ] `prompts/confirmation_parser.md` and `prompts/macro_estimation.md` updated to match new schemas.
- [ ] Original bug ("1 piece of chicken" → 1 gram) is fixed: smoke confirms ~130g.
- [ ] All level 1-4 validation commands pass with zero errors.
- [ ] No code paths reference `default_unit` or `default_unit_weight_g` (only commit_logs/ and docs/plans/).
- [ ] `tests/unit/test_food_service_helpers.py` covers all 5 branches of the resolver.
- [ ] At least 4 new integration tests in `test_food_service_unit_resolution.py`.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit + integration + graph-api)
- [ ] No linting or type checking errors
- [ ] Manual smoke testing confirms feature works
- [ ] Acceptance criteria all met
- [ ] CSV file (`data/canonical_food_catalog.csv`) migrated and re-seeded
- [ ] Old columns dropped from Supabase
- [ ] Commit log written for the PR

---

## NOTES

### Why we chose this design (summarized from planning conversation)

Three iterations took us here:

1. **Original idea**: lazy LLM backfill in `calculate_macros_node` — extra LLM call per first-encounter (food, unit). Worked but added latency + complexity.
2. **User's improvement**: have the input parser also emit `amount_g` — zero extra LLM calls, ride on the call already happening. Adopted.
3. **User's deeper question**: "why have a `default` unit at all?" — surfaced that the schema needed multi-unit support. Adopted: `unit_weights` map.
4. **Final simplification**: drop the `Literal` constraint and the parser's normalization. The synonym table already handles "user-said-X → canonical-Y" matching. Doing it in the parser AND in the resolver is duplicate logic that can drift. Move all matching to the resolver. Parser just emits what the user said + an estimated weight.

### V1 explicitly excluded: self-heal

We discussed but rejected having the system write back to `unit_weights` when the LLM-estimated `amount_g` is used. Coach-curated only. Reason: the "rogue first estimate gets pinned forever" risk + matches FitPal's coach-as-authority model. The resolver chain still handles uncurated units gracefully via the LLM estimate fallback — there's just no persistence of that estimate. If the same (food, unit) is logged 100 times, the LLM re-estimates 100 times (each estimate may vary by ~5%). Acceptable v1 cost. Self-heal can be added later as a separate feature.

### V1 explicitly excluded: synonym-suggestion UI

Coach curates `unit_synonyms` manually. No "looks like a duplicate, want to merge?" hints in v1. Future work.

### Coach reference — adding a synonym reactively

When you notice users hitting the LLM-fallback path frequently for a particular (food, unit), curate the synonym directly in Supabase. The `||` operator merges into the existing JSONB without overwriting other entries.

**Add a single synonym:**
```sql
UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"piece": "slice"}'::jsonb
WHERE name_en = 'pizza';
```

**Add a Hebrew alias for an existing English-curated unit:**
```sql
UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"פרוסה": "slice"}'::jsonb
WHERE name_en = 'pizza';
```

**Add multiple synonyms at once:**
```sql
UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"piece": "slice", "פרוסה": "slice", "wedge": "slice"}'::jsonb
WHERE name_en = 'pizza';
```

**Add a brand-new unit weight (not a synonym — actually has a different gram value):**
```sql
UPDATE food_items
SET unit_weights = unit_weights || '{"slice": 30}'::jsonb
WHERE name_en = 'chicken_breast';
-- Now chicken has both "piece" (130g, the whole breast) and "slice" (30g, deli)
```

**Inspect what's already curated for a food:**
```sql
SELECT name_en, name_he, unit_weights, unit_synonyms
FROM food_items
WHERE name_en ILIKE '%pizza%';
```

**Find foods that are getting the LLM fallback most often** (for prioritized curation — requires a future log query, sketch only):
```sql
-- Pseudocode: find (food_id, original_unit) pairs in daily_logs where
-- the food's unit_weights doesn't contain original_unit AND unit_synonyms doesn't either.
-- These are the foods worth curating next.
```

### Deferred: input parser eval dataset update

The existing `notebooks/evals/eval_input_parser.ipynb` likely has expected outputs constrained to the old `Literal[g, piece, slice, ...]`. After this PR, the parser is free-form. The eval dataset should be reviewed and reference outputs regenerated — but this is a separate ticket. Bundling here would couple unrelated lifecycles.

### Deferred: Hebrew synonym seeding

The seed CSV doesn't currently carry `unit_synonyms`. Coach should seed common Hebrew aliases (e.g., for pizza: `{"פרוסה": "slice", "חתיכה": "slice"}`) — but this is content work, not code work. Out of scope for this PR; ship empty `unit_synonyms` and let the coach curate iteratively.

### Risks

- **Parser quality regression**: dropping the static 28-food reference table may degrade parser accuracy on the foods previously hardcoded. Mitigation: the LLM has general knowledge; the safety net (`amount_g` estimate + resolver fallback chain) absorbs most parser noise. Worth re-running the input parser eval after this PR to measure.
- **Mid-rollout breakage**: Phase 1 adds columns but Phase 5 drops them. Between, the bot should keep working because we backfill in Phase 1 and the old columns stay readable until Phase 5. Order of operations matters — follow the plan strictly.
- ~~**Race during re-seed**~~: Removed. Phase 5.3 no longer re-seeds — existing curated data is preserved by Phase 1.1's backfill.

### Confidence: 8/10 for one-pass success

Reasoning:
- Strong: well-scoped refactor, clear before/after for each file, validation commands at every step.
- Risk: prompt rewrites may need iteration after manual smoke (parser may get cute with units in surprising ways). Plan accommodates this — Phase 6.5 is the empirical validation.
- Risk: the CSV migration helper (5.1) needs the user to actually have the CSV; if they don't, that step needs adaptation.
