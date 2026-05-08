# PR Reading Guide — HITL preview natural-unit rendering + unit-aware edits

## Why
- **Plan**: [`hitl-preview-natural-units.md`](./hitl-preview-natural-units.md) — UX Fix #4. Decisions are locked in the plan's `## NOTES` section (don't re-litigate).
- **Commit log**: [`2026-05-08_18-38-21_hitl-natural-units.md`](../../commit_logs/2026-05-08_18-38-21_hitl-natural-units.md) — what / why / deferred.
- **Precedent**: PR #28 (Fix #5, `consumed_at` date label) — same area, same i18n pattern, same test structure.

## Suggested reading order

The two state fields (`original_count`, `original_unit`) are the keystone — every other change either *writes* them, *reads* them, or *renders* them. Read in causality order:

1. **`src/agents/state.py`** — the keystone. Two fields added to `MacroResult`. Required (not Optional); see plan NOTES `## Why original_unit: str is required`.

2. **`src/schemas/estimation_schema.py`** — required `amount_g_estimated` on `MacroEstimation`. This drives the estimation-path fix (Option C): the LLM now states the gram total directly instead of us inferring `count × default_unit_weight_g`.

3. **`src/schemas/confirmation_schema.py`** — `ItemEdit` replaces `new_amount_g` with `(new_count, new_unit)`. The unit Literal mirrors `SingleFoodItem.unit` verbatim — keep them in sync.

4. **`src/agents/nodes/calculate_macros_node.py`** — the writer. DB path populates new fields from local `count`/`unit`. `_estimate_macros` signature changes from `(food_name, amount_g, original_text)` → `(food_name, count, unit, original_text)`; the estimated `MacroResult.amount_g` now comes from `result.amount_g_estimated`. Removing `amount_g = count` is the natural-unit estimation-path bug fix.

5. **`prompts/macro_estimation.md`** — instructs the LLM on the new contract. Section 1 has worked examples (`count=2, unit="slice"` → `amount_g_estimated=200`). Section 6 makes `default_unit_weight_g` required for natural-unit input. Bold *"for that **exact gram total**"* is intentional — without it the LLM reverts to per-100g macros.

6. **`src/agents/nodes/confirmation_node.py`** — the readers + render side, in this internal order:
   - `_unit_label_key` helper (singular/plural picker).
   - `_format_batch_preview` render rule: grams renders as `Xg` (unchanged); natural unit renders as `{count} {label} ({amount_g}g)`. Uses `f"{count:g}"` to strip `.0`.
   - `_parse_confirmation` batch_context: now includes `original_count` + `original_unit` per item so the LLM can apply count-only inheritance.
   - `_surface_edit_error` helper.
   - `_apply_edits` rewrite: signature returns `(batch, edit_errors)`. DB branch uses tool's `(count, unit)`; estimated branch converts via `default_unit_weight_g`; mismatch path appends a FAILED `ProcessingResult` and `continue`s (loop keeps going for other edits).
   - `confirmation_node` body: `accumulated_edit_errors` list across loop iterations, merged into the `update` field of all final `Command`s — both confirm and reject paths. Mutating `state` directly wouldn't survive LangGraph's state merge.

7. **`prompts/confirmation_parser.md`** — rewritten rules + examples. Old "Parse amounts to grams" rule **removed** (was wrong post-change). The Examples section is load-bearing for inheritance behavior; the eval (deferred) will lock this in.

8. **i18n trio** — `src/i18n/__init__.py` (TypedDict), `src/i18n/en.yaml`, `src/i18n/he.yaml`. 16 keys per language, alphabetical by unit, singular before plural. No `g` keys (grams use the `Xg` suffix). The boot-time parity check refuses to start on drift between the three.

9. **Tests — regression-first**:
   - `tests/unit/test_calculate_macros_node.py`: `_estimate_return` helper + 3 estimation-path tests (grams pass-through, natural-unit uses LLM `amount_g_estimated`, HumanMessage carries count + unit). The third is a defensive check that's easy to lose in refactors.
   - `tests/unit/test_confirmation_node.py`: `SAMPLE_BATCH` updated to carry the new fields; `test_edit_loops_and_re_shows` updated for the new `ItemEdit` shape; 3 render tests + 3 edit tests added (natural-unit DB edit, estimated unit conversion, estimated unit-mismatch surfaces FAILED result).

## Things worth flagging while reviewing

1. **Edit-error accumulation across loop iterations**. `_apply_edits` is now pure-ish (returns errors instead of mutating state). `confirmation_node` accumulates them in a local list and merges into the `update` field of *both* confirm and reject Commands. Direct `state["processing_results"]` mutation looks tempting but doesn't survive LangGraph's merge — only `Command.update` does. Worth a sanity check that the merge semantics match the rest of the codebase.

2. **Render uses `MESSAGES` (import-time language), not runtime lookup**. The bot is single-language per process (`BOT_LANGUAGE` env var) and restarts on deploy, so this matches the existing pattern (see Fix #5). If we ever want per-user language without restart, this lookup needs to move to runtime.

3. **Unit-test assertions are language-agnostic**. The render tests assert against `MESSAGES["confirmation_unit_label_slice_plural"]` rather than literal `"slices"` — because devs may have `BOT_LANGUAGE=he` in their shell when MESSAGES is imported. The plan assumed default-en; reality is "depends on shell env". This keeps tests green either way.

4. **Estimated unit-mismatch falls through cleanly, not loudly**. `_apply_edits` continues processing other edits when one fails — `continue`, not `break`. Multi-edit batches with one bad edit will produce one FAILED result and apply the rest. Plan-intentional, but worth confirming this matches the rest of the codebase's error-handling philosophy.

5. **`MacroResult.original_unit` is `str`, not the same Literal as `SingleFoodItem.unit`**. Pragmatic: TypedDicts don't enforce at runtime anyway and the writer is sole producer. If we ever add a unit, the Literal in `ItemEdit.new_unit` + `SingleFoodItem.unit` + `MacroEstimation.default_unit` must update together (called out in plan NOTES).

6. **No eval in this PR**. The confirmation-parser mechanic is changing in this PR (new schema, new prompt, new inheritance behavior). Eval is deferred to a follow-up — building it now would mean churning reference outputs through implementation. Brain TASKS follow-up will add a ~40-case dataset (70% he / 30% en) with code-based evaluators.

## Skip-able

- `src/i18n/he.yaml` and `src/i18n/en.yaml` additions — mechanical mirror of the TypedDict.
- The plan doc itself (`docs/plans/hitl-preview-natural-units.md`) — long; the commit log + this guide are the synthesis.
- Updated `SAMPLE_BATCH` literal in `test_confirmation_node.py` — purely a fixture extension.
