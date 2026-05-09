# HITL preview natural-unit rendering + unit-aware edits + estimation-path fix

**Plan**: `docs/plans/hitl-preview-natural-units.md`
**Branch**: `ux/hitl-preview-natural-units`

## What changed

Three coordinated changes that share two new state fields (`MacroResult.original_count`, `MacroResult.original_unit`):

### 1. Carry the user's natural unit through the pipeline
`calculate_macros_node` now populates `original_count` + `original_unit` on every `MacroResult` (DB and estimation paths). These fields are required (not Optional) — the writer is the only producer; making them required surfaces forgotten code paths immediately.

### 2. Estimation path natural-unit fix (Option C)
Pre-fix, `calculate_macros_node` collapsed non-grams units to grams before estimation, so *"2 פרוסות פיצה"* got estimated for **2 grams** of pizza. Now:
- `MacroEstimation` schema gained a required `amount_g_estimated: float` field.
- `prompts/macro_estimation.md` accepts `(food_name, count, unit)`, instructs the LLM to compute `amount_g_estimated = count × default_unit_weight_g` for natural-unit input, and to emit macros for that exact gram total.
- `_estimate_macros` signature changed to `(food_name, count, unit, original_text)`; `MacroResult.amount_g` now comes from `result.amount_g_estimated`.

### 3. Render natural units in HITL preview + accept unit-aware edits
- `_format_batch_preview` renders `{name} — {count} {label} ({amount_g}g)` when `original_unit != "g"`. Unit labels added to i18n (16 keys × 2 languages = 32 values, alphabetical, singular + plural).
- `ItemEdit` schema replaced `new_amount_g` with `(new_count, new_unit)`. The Literal value list mirrors `SingleFoodItem.unit`.
- `prompts/confirmation_parser.md` rewritten with explicit examples: emit both fields, inherit `new_unit` from `original_unit` on count-only edits.
- `_apply_edits` rewritten:
  - DB items pass `(count, unit)` straight to `calculate_food_macros`.
  - Estimated items convert via `default_unit_weight_g`; mismatch surfaces a FAILED `ProcessingResult` without crashing the loop.
  - Returns `(updated_batch, edit_errors)` — caller accumulates errors and merges them into the final `Command` update so they survive the LangGraph state merge.
- `_parse_confirmation` batch_context now includes `original_count` + `original_unit` so the LLM can apply the inheritance rule.

## Why

Users phrasing logs in natural units ("2 slices of cheese") saw `50g` in the HITL preview and had to do unit-conversion math to edit ("2 slices → 3 slices ≈ 75g"). The preview felt wrong even when the underlying gram math was right; rejection rate was high. This fix makes the preview match the user's mental model and lets edits stay in natural units. Folded the estimation-path natural-unit bug into the same PR because it shares the new `(count, unit)` plumbing.

## Validation

- `uv run ruff check src/ bot/ tests/` — clean
- `uv run pytest tests/unit/` — 177 passed (9 new tests: 3 render, 3 estimation-path, 3 edit-side)
- `uv run pytest tests/integration/` — 47 passed

## Deferred / next steps

- **Eval (TASKS follow-up)**: Build a `confirmation_parser` eval covering the new `(count, unit)` shape, count-only inheritance, removes, multi-edit, language mix. ~40 cases, 70% he / 30% en. Code-based evaluators (correct_action, correct_edit_count, correct_edit_types, correct_item_indices, correct_change_amount_payload, unit_inheritance_correct). Mirror input-parser eval structure. Bundling it here would couple unrelated lifecycles and require churning reference outputs through implementation.
- **Manual smoke**: 6 flows × 2 languages — confirm, reject, grams edit, natural-unit edit, count-only inheritance, off-menu natural-unit estimation. Documented as PR-description checkboxes.
