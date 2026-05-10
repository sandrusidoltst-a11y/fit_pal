# PR Review Guide — Multi-Unit Weights + Synonyms

**Plan**: `docs/plans/multi-unit-weights-and-synonyms.md`
**Commit log**: `commit_logs/2026-05-10_multi-unit-weights-and-synonyms.md`

## Reading Order

### 1. Why — start here
Read the commit log to understand the confirmed bug ("1 piece of chicken" → 1g) and the three root causes (single-unit schema, parser Literal coercion, no edit fallback).

### 2. Keystone — the contract changes
- `src/schemas/input_schema.py` — `SingleFoodItem.unit` goes from `Literal[9]` to free-form `str`; new `amount_g: Optional[float]`
- `src/schemas/confirmation_schema.py` — `ItemEdit.new_unit` same; new `new_amount_g`
- `src/schemas/estimation_schema.py` — estimator stripped of all weight/unit fields
- `src/agents/state.py` — `PendingFoodItem` gains `amount_g`; `MacroResult` swaps `default_unit`/`default_unit_weight_g` for `amount_g_estimated`

### 3. The resolver — the core fix
`src/services/food_service.py` — `resolve_amount_g` (5-step chain), `compute_food_macros` (new return keys), `calculate_food_macros` tool (new `llm_estimated_amount_g` param, removed try/except), `create_food_item_record` + `create_food_item` (new params).

### 4. Nodes — consumers of the new shape, in dependency order
1. `src/agents/nodes/calculate_macros_node.py` — DB path threads `amount_g`; `_estimate_macros` now takes `amount_g` from parser
2. `src/agents/nodes/confirmation_node.py` — defensive i18n lookup; `_apply_edits` new resolver path for both DB and estimated items
3. `src/agents/nodes/commit_node.py` — one-liner: estimated foods write `unit_weights={}`/`unit_synonyms={}`

### 5. Prompts
- `prompts/input_parser.md` — section 2.7 (28-food table) deleted; Step 2 rewritten for free-form unit + `amount_g`
- `prompts/confirmation_parser.md` — full rewrite to match new `ItemEdit` shape
- `prompts/macro_estimation.md` — full rewrite: estimator gets gram total in human message, emits macros only

### 6. Schema (DB layer)
`src/models.py` — JSONB import; `unit_weights`/`unit_synonyms` columns added; old columns removed.
Two Supabase migrations applied (not in this diff — applied via MCP):
1. ADD `unit_weights`/`unit_synonyms` + backfill 32 rows
2. DROP `default_unit`/`default_unit_weight_g`

### 7. Scripts
- `src/scripts/seed_canonical_catalog.py` — reads new JSON columns from CSV
- `src/scripts/migrate_csv_to_unit_weights.py` (new) — idempotent CSV converter

### 8. Tests — new guards first, then fixture updates
- `tests/unit/test_food_service_helpers.py` — full rewrite: 7 tests covering all 5 resolver branches (grams, direct hit, synonym, broken-synonym fallthrough, estimate, last-resort)
- `tests/integration/test_food_service_unit_resolution.py` (new) — 5 real-DB tests, one per resolver branch
- Fixture updates (low signal — just field renames): `tests/conftest.py`, `tests/unit/test_calculate_macros_node.py`, `tests/unit/test_commit_node.py`, `tests/unit/test_confirmation_node.py`, `tests/unit/test_feedback_logic.py`, `tests/unit/test_multi_item_loop.py`, `tests/integration/test_log_yesterday_e2e.py`

---

## Things Worth Flagging

1. **Parser quality regression risk** — removing the 28-food static table means the parser now relies on general LLM knowledge for unit selection. The `amount_g` safety net absorbs the resolver's downside, but `food_name` quality could drift if the parser gets creative. Worth re-running `notebooks/evals/eval_input_parser.ipynb` post-merge (deferred — eval outputs were constrained to the old Literal enum and need regeneration first).

2. **Estimated foods commit with empty `unit_weights`** — `commit_node` writes `{}` for estimated rows. This means the same (food, unit) re-logged by the user hits the LLM fallback every time until a coach curates it. Intentional v1 decision (coach-curated-only, no self-heal), but worth knowing the repeat-estimate frequency could motivate a curation workflow later.

3. **Synonym seed is data, not code** — the 8 `UPDATE` statements were run directly on Supabase, not through a migration file. They're documented in the commit log but not in `supabase/migrations/`. If the DB is ever wiped and reseeded from scratch, these synonyms won't be replayed automatically — the coach would need to re-run the synonym seed or add it to the seed script.

4. **`_estimate_macros` fallback when `amount_g is None`** — if the parser fails to emit `amount_g` for a natural-unit input, the estimator falls back to treating `count` as grams (with a warning log). This is the same last-resort as `resolve_amount_g`. Acceptable, but could produce wrong macros for natural-unit off-menu foods if the parser regresses on `amount_g` emission.

5. **Defensive `MESSAGES.get(...)` in `_format_batch_preview`** — previously crashed on unknown units; now renders the raw unit string verbatim. Confirm the fallback renders acceptably in the Telegram bot for Hebrew-language units not in the i18n table.

---

## Skip-able
- `tests/unit/test_calculate_macros_node.py` beyond the estimation path tests — mostly field-rename churn (`default_unit` → `amount_g_estimated`, added `llm_estimated_amount_g` to call args).
- `tests/unit/test_confirmation_node.py` fixture blocks (lines 285–320, 375–400, 455–470, 505–515) — mechanical `default_unit_weight_g` → `amount_g_estimated` renames.
- `docs/plans/multi-unit-weights-and-synonyms-curation.sql` — scratch SQL for the coach, not part of the application.
