# Multi-Unit Weights + Synonyms

**Date**: 2026-05-10
**Branch**: `feat/multi-unit-weights-and-synonyms`
**Plan**: `docs/plans/multi-unit-weights-and-synonyms.md`

## Why

Confirmed bug (PR #29, commit `873791e`): "1 piece of chicken" was logged as 1 gram (~1.6 kcal). Root cause: the resolver silently fell back to treating `count` as grams whenever the user's unit didn't match the food's single curated `default_unit`. Three tightly coupled issues: single-unit schema, parser-side normalization (9-value Literal enum forcing coercion), and no edit-side fallback for estimated items.

## What Changed

### Schema (Supabase + SQLAlchemy)
- Added `unit_weights JSONB NOT NULL DEFAULT '{}'` and `unit_synonyms JSONB NOT NULL DEFAULT '{}'` to `food_items`.
- Backfilled 32 curated rows from the legacy `(default_unit, default_unit_weight_g)` column pair.
- Dropped `default_unit` and `default_unit_weight_g`.
- Seeded 28 food rows with coach-curated synonym maps (Hebrew + English alternates per canonical unit).

### Resolver (`src/services/food_service.py`)
- `resolve_amount_g` rewritten as a 5-step chain: `unit=="g"` passthrough → `unit_weights` direct hit → `unit_synonyms` redirect → `llm_estimated_amount_g` safety net (parser's estimate) → last-resort count-as-grams with warning log. Never raises; never crashes.
- `compute_food_macros` now returns `unit_weights`/`unit_synonyms` instead of `default_unit`/`default_unit_weight_g`.
- `calculate_food_macros` tool gains `llm_estimated_amount_g: Optional[float]` param.
- `create_food_item_record` + `create_food_item` tool: replaced `default_unit`/`default_unit_weight_g` params with `unit_weights`/`unit_synonyms`.

### Schemas
- `SingleFoodItem.unit`: `Literal[9 values]` → free-form `str`. New `amount_g: Optional[float]` — parser's total-gram estimate, required when `unit != "g"`.
- `ItemEdit.new_unit`: same Literal → free-form `str`. New `new_amount_g: Optional[float]`.
- `MacroEstimation`: stripped of `amount_g_estimated`, `default_unit`, `default_unit_weight_g`. Estimator now receives the gram total from the parser and only emits macros + names + category + tag.

### State
- `PendingFoodItem`: new `amount_g: Optional[float]` field (mirrors `SingleFoodItem`, populated by `model_dump()` from input_node).
- `MacroResult`: replaced `default_unit`/`default_unit_weight_g` with `amount_g_estimated: Optional[float]` (parser's estimate carried for edit-side fallback).

### Nodes
- `calculate_macros_node`: DB path threads `current_item.get("amount_g")` as `llm_estimated_amount_g` into the tool call. Estimation path: `_estimate_macros` now takes `amount_g` from parser and uses it as `resolved_amount_g` (fallback to `count` with warning when missing); passes gram total in human message so estimator is accurate.
- `confirmation_node._apply_edits`: DB branch passes `edit.new_amount_g` as `llm_estimated_amount_g`. Estimated branch: `g` → count, `new_amount_g` present → use, same unit → proportional scale, else → error. Defensive i18n label lookup (`MESSAGES.get(...)`) so unknown free-form units render verbatim instead of raising.
- `commit_node`: estimated foods write `unit_weights={}`, `unit_synonyms={}` (coach curates later).

### Prompts
- `input_parser.md`: removed maintenance note + section 2.7 (28-food static reference table). Step 2 rewritten: unit is free-form, parser must emit `amount_g` when `unit != "g"`. Hebrew quantifier examples updated. Output format spec updated.
- `confirmation_parser.md`: full rewrite — `new_unit` free-form, `new_amount_g` required when non-gram, added unrecognized-unit example.
- `macro_estimation.md`: full rewrite — estimator consumes supplied gram total, no longer emits weight/unit metadata.

### Scripts
- `seed_canonical_catalog.py`: reads `unit_weights`/`unit_synonyms` JSON columns from CSV; `_to_json_dict` helper.
- `migrate_csv_to_unit_weights.py` (new): idempotent helper to convert the local `data/canonical_food_catalog.csv` from the legacy column pair to the new JSON format.

## Validation
- ruff: ✅ clean
- unit tests: ✅ 179 passed
- integration tests (real Supabase, incl. 5 new resolver-chain tests): ✅ 52 passed
- Supabase migrations applied: ADD+backfill + DROP (in order, no data loss)
- Synonym seed: 28 food rows populated

## Next Steps
- Run graph-api E2E (`uv run pytest tests/graph_api/ -v -s`)
- Manual smoke via dev bot: "1 piece of chicken", "כף טחינה", "קופסת טונה", edit flow
- Run input parser eval (`notebooks/evals/eval_input_parser.ipynb`) — reference outputs constrained to old Literal enum; regenerate post-merge
- Coach can add more synonyms reactively via `UPDATE food_items SET unit_synonyms = unit_synonyms || '{"..."}'::jsonb WHERE name_en = '...'`
