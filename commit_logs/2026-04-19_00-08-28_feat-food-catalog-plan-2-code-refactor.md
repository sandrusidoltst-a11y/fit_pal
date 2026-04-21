# feat: food catalog migration Plan 2 — services/nodes/i18n consume two-table schema; drop legacy name column

**Date:** 2026-04-19
**Commit:** `e27e8e9`
**Branch:** `refine_prompts_and_evals`
**Plan:** [docs/plans/food-catalog-code-refactor.md](../docs/plans/food-catalog-code-refactor.md)

---

## Summary

Plan 2 of 3 in the food catalog refactor. Rewrites every food-catalog code path (services, `@tool` wrappers, graph nodes, Pydantic schemas, state TypedDicts, i18n, bot HITL renderer) to consume the two-table schema landed in Plan 1: `food_items` (universal facts) joined with `coach_food_mappings` (coach-method overlay). Adds bilingual search, unit/count resolution, servings math, and category-aware HITL rendering. Drops the legacy `food_items.name` column via Supabase migration and reseeds.

LLM prompts are intentionally deferred to Plan 3 — the bot is end-to-end broken between Plan 2 and Plan 3 (schemas expect `count`/`unit`, parser prompt still says "extract grams"). Correctness gate is tests, not bot behavior.

---

## Changes

### Schemas (Pydantic)

- `src/schemas/input_schema.py` — `SingleFoodItem`: `amount: float` → `count: float`; `unit` widened from `Literal["g"]` to `Literal["g", "piece", "slice", "scoop", "bottle", "cup", "tbsp", "tsp", "can"]`.
- `src/schemas/estimation_schema.py` — added optional `name_en`, `name_he`, `category`, `tag`, `default_unit`, `default_unit_weight_g` fields (teaches LLM to produce coach-method-aware output).

### State TypedDicts

- `src/agents/state.py`:
  - `PendingFoodItem`: `amount` → `count`
  - `SearchResult`: replaced `name` with `name_en`/`name_he` + added `category`/`tag`
  - `MacroResult`: added `name_en`/`name_he`/`category`/`tag`/`servings`/`serving_amount_g`/`default_unit`/`default_unit_weight_g`
  - `ProcessingResult`: carries `name_he` + inherited `count`

### Service Layer

- `src/services/food_service.py` — full rewrite:
  - **Pure helpers**: `resolve_amount_g(food, unit, count)` (unit→grams), `compute_servings(amount_g, serving_amount_g)` (grams→servings), `compute_food_macros(food, mapping, amount_g)` (enriched macro dict)
  - **Service functions**: `search_food_items` (bilingual LEFT JOIN, tier 1 database → tier 2 estimated), `get_food_by_id` (returns `(FoodItem, Optional[CoachFoodMapping])` tuple), `create_food_item_record` (atomic food + mapping when `category` provided)
  - **@tool wrappers**: `search_food` (returns id/name_en/name_he/source/category/tag), `calculate_food_macros` (enriched dict via pure helper), `create_food_item` (new signature with all mapping fields)

### Graph Nodes

- `selection_node.py` — `search_context` shows `name_en / name_he [category,tag]` per candidate
- `calculate_macros_node.py` — DB path now uses `get_food_by_id` + `resolve_amount_g` + pure `compute_food_macros` (single query per item, no tool round-trip); estimation path carries LLM-emitted names/category/unit
- `confirmation_node.py` — BOT_LANGUAGE-aware rendering (Hebrew name when `name_he` present), servings/category surfaced in preview payload, reject/parse branches reference new field names
- `commit_node.py` — calls `create_food_item` with new signature (name_en/name_he + all mapping fields); `ProcessingResult` gets `name_he` + `count` (post-resolution grams)

### i18n

- Added `confirmation_serving_line` + 6 `confirmation_category_label_*` keys to `Messages` TypedDict + both `en.yaml` and `he.yaml`. Startup parity check passes.

### Bot Gateway

- `bot/gateway.py _format_interrupt_value` — inserts `~{servings} {category_label} serving(s)` line beneath each item when `servings` + `category` are present; falls back gracefully on unknown categories.

### Seed + Migration

- `src/scripts/seed_canonical_catalog.py` — dropped legacy `name` column from INSERT SQL
- `src/models.py` — removed `name` field from `FoodItem`
- **Supabase migration applied**: `drop_legacy_food_items_name_column` (`ALTER TABLE food_items DROP COLUMN name`)
- **Reseeded**: 93 `database`-source food_items + 93 `coach_food_mappings` under `DEFAULT_COACH_ID`

### Tests

- New: `tests/unit/test_food_service_helpers.py` (13 tests for `resolve_amount_g`, `compute_servings`, `compute_food_macros`)
- Rewrote `tests/unit/test_calculate_macros_node.py` to mock `get_food_by_id` + async session patch
- Updated fixtures + assertions in: `test_confirmation_node.py`, `test_commit_node.py`, `test_food_search_node.py`, `test_agent_selection.py`, `test_feedback_logic.py`, `test_multi_item_loop.py`, `test_input_parser.py`
- Updated `tests/conftest.py` to seed `FoodItem` + paired `CoachFoodMapping` under `DEFAULT_COACH_ID`
- Updated `tests/integration/test_food_service.py`: added `TestBilingualSearch`, `TestCoachMappingJoin` (including LEFT JOIN no-match assertion), atomic category→mapping test
- Updated `tests/integration/test_daily_log_model.py`: `food_item.name` → `food_item.name_en`

---

## Validation

| Check | Result |
|---|---|
| `ruff check src/ bot/ tests/` | ✅ Clean |
| `pytest tests/unit/` | ✅ 147/147 passed |
| `pytest tests/integration/` | ✅ 40/40 passed (1m 47s) |
| Supabase DB state | ✅ `food_items.name` dropped; 93 canonical + 93 mappings |

Graph-API tests intentionally skipped (prompts stale → predictable failures; resumes in Plan 3).

---

## Known Breakage (Accepted)

After this commit the bot will NOT work correctly end-to-end:

- Parser prompt still says "extract grams" → for "2 eggs" it emits `{count: 100, unit: "g"}` instead of `{count: 2, unit: "piece"}` → macros computed against 100g of egg
- Estimation LLM won't populate `name_he`/`category`/`tag`/`default_unit` (Optional, no crash — but created food items carry only English name, no coach mapping)
- Response prompt has no awareness of servings/categories → responses won't mention them

Smoke tests with unambiguous gram-input ("200g chicken") should still work.

---

## Next Steps — Plan 3

**Scope: prompts only, no schema or code changes.**

1. `prompts/input_parser.md` — drop "translate to English"; emit `{count, unit}`
2. `prompts/macro_estimation.md` — teach LLM to fill `name_en`/`name_he`/`category`/`tag`/`default_unit`/`default_unit_weight_g`
3. `prompts/agent_selection.md` — use `category`/`tag` for selection quality
4. `prompts/response_generator.md` — coach voice with serving math + category grouping
5. `prompts/confirmation_parser.md` — accept unit-based edits ("change eggs to 3") via `new_count`/`new_unit` in `ItemEdit`
6. HITL copy iteration (Hebrew wording refinement)
7. Re-run evals + add estimation-quality eval

Schema sufficiency: ✅ verified — all fields Plan 3 prompts need already exist in Plan 2 schemas.
