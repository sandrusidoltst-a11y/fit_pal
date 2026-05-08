# Feature: HITL preview natural-unit rendering + unit-aware edits (UX Fix #4)

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files.

> **Branch**: `ux/hitl-preview-natural-units` (already created from `main`).
>
> **Scope**: Fix #4 — render natural units in HITL preview + accept unit-aware edits + fix the estimation-path natural-unit bug along the way (Option C).
>
> **Decisions are LOCKED** — see the `## NOTES` section at the bottom for the reasoning. Don't re-litigate during implementation.
>
> **Commit shape**: not prescribed by the plan. Execute the tasks below in order, then use the `/commit` skill to package the result. The natural break point (if you split into commits) is between task 12 (last render-side task) and task 13 (first edit-side task) — render-side is purely additive and could ship as a standalone increment. But that's a post-execution decision.
>
> **Eval is deferred to a follow-up PR** (separate session). Reasoning: the confirmation-parser mechanic is changing in this PR (new schema shape, new prompt rules, new inheritance behavior). Building an eval *before* the new mechanic stabilizes means churning reference outputs through implementation. Building the eval *after* this lands lets it lock in the intended final shape and act as a durable regression guard for future changes. For THIS PR, validation is via unit tests + dev-bot manual smoke covering all 6 flows × 2 languages.
>
> **Add to brain TASKS.md (manually, separate repo)** as a follow-up: *"Build confirmation_parser eval — covers new `(count, unit)` shape, count-only inheritance, removes, multi-edit, language mix. Dataset ~40 cases, 70% he / 30% en. Code-based evaluators (correct_action, correct_edit_count, correct_edit_types, correct_item_indices, correct_change_amount_payload, unit_inheritance_correct). Mirror input-parser eval structure (notebook + script)."*

## Feature Description

When a user logs a food in a natural unit (*"שתי פרוסות גבינה"* / "two slices of cheese"), the HITL confirmation preview today renders `<name> — Xg` regardless of the unit the user actually used. The preview shows `50g`, not `2 פרוסות`. Users often reject the message because it looks wrong — even though the underlying gram math is correct.

Worse: if the user wants to bump *"2 פרוסות"* to *"3 פרוסות"*, the only edit grammar they have is grams (`new_amount_g`). They have to do their own conversion math (~75g for 3 slices? hard to know) or reject and re-log.

This fix:
1. **Renders the user's natural unit** in the preview when it differs from grams.
2. **Lets users edit in either grams or the natural unit**, with the LLM inferring the unit from context when the user just gives a count.

## User Story

As a **FitPal user logging food in natural units**,
I want to **see the preview in the units I just spoke in (e.g., "2 slices") and adjust quantities in those same units**,
So that **the preview matches my mental model and editing feels like a natural conversation, not unit-conversion homework**.

## Problem Statement

Today's `_format_batch_preview` in `src/agents/nodes/confirmation_node.py` builds the per-item description as `f"{name} — {item['amount_g']}g{source_tag}"`. The user's `count` and `unit` from `PendingFoodItem` are dropped at the calc-macros step — they never make it onto `MacroResult`. By the time the preview is built, all the system has is `amount_g`.

Today's `ItemEdit` schema in `src/schemas/confirmation_schema.py` has `new_amount_g: Optional[float]` only. The LLM cannot emit "3 slices"; it must compute or guess the gram equivalent. The confirmation parser prompt explicitly tells the LLM to "parse amounts to grams". For DB items the existing tool already accepts `(count, unit)`; the only thing standing in the way is the schema field. For estimated items the `_apply_edits` branch does proportional gram scaling and has no path for natural-unit edits.

Net effect: the user's natural-unit phrasing is silently translated to grams at log time and never resurfaces. The preview is internally correct but externally feels wrong; edits force the user back into grams.

## Solution Statement

Three coordinated changes that share the same `original_count`/`original_unit` fields on `MacroResult`. Tasks below are one linear sequence; commit shape is decided post-execution via `/commit`.

**1. Carry the user's natural unit through `calculate_macros_node` onto `MacroResult`.** Add required `original_count: float`, `original_unit: str` fields to `MacroResult`. Both DB path and estimation path populate them from the user's stated `(count, unit)`.

**2. Fix the estimation-path natural-unit bug along the way (Option C).** Today `calculate_macros_node` collapses non-grams units to grams before calling `_estimate_macros` (`amount_g = count` regardless of `unit`). So *"2 פרוסות פיצה"* gets estimated for 2g instead of 2 slices. We extend `MacroEstimation` with a required `amount_g_estimated: float`, update `prompts/macro_estimation.md` to accept `(count, unit, food_name)` and emit consistent macros + `amount_g_estimated`, and update `_estimate_macros` to pass through the user's natural unit. The LLM is responsible for the gram math (it must already know "1 slice of pizza ≈ 100g" to populate `default_unit_weight_g` correctly today). After this fix, the user's natural unit round-trips faithfully through the estimation path — preview shows *"2 פרוסות פיצה (200g)"*.

**3. Render natural units in the preview AND accept unit-aware edits.** Update `_format_batch_preview` to render natural units when `original_unit != "g"`. Add 32 i18n keys (8 units × 2 forms × 2 langs) for unit labels. Replace `ItemEdit.new_amount_g` with `(new_count: Optional[float], new_unit: Optional[Literal[...]])` — same Literal as `SingleFoodItem.unit`. Update `_apply_edits` for both branches: DB items pass-through to `calculate_food_macros` (already accepts `(count, unit)`); estimated items use `default_unit_weight_g` to convert when unit matches `default_unit`, else surface a clean error. Update `prompts/confirmation_parser.md` to emit both fields and to inherit `new_unit` from `original_unit` on count-only edits. Update `_parse_confirmation` batch_context to include `original_count`/`original_unit` so the LLM can do the inheritance.

The render side (tasks 1-12) and edit-grammar side (tasks 13-19) share the new state fields and ship as one cohesive change. Render side is purely additive; edit side carries the prompt risk and is where the deferred eval will pay off long-term.

**No eval in this PR** — confirmation-parser eval is deferred to a follow-up PR (see top-of-plan callout). Validation for THIS PR comes from: full unit suite + integration suite + dev-bot manual smoke covering all 6 flows × 2 languages.

## Feature Metadata

**Feature Type**: Enhancement (UX gap — preview rendering + edit grammar)
**Estimated Complexity**: Medium-high — ~12 files touched across two commits, includes two Pydantic schema changes (`ItemEdit`, `MacroEstimation`) and two load-bearing prompt changes (`confirmation_parser.md`, `macro_estimation.md`).
**Primary Systems Affected**:
- `src/agents/state.py` (`MacroResult` shape)
- `src/agents/nodes/calculate_macros_node.py` (populate new fields + pass `(count, unit)` to estimation)
- `src/agents/nodes/confirmation_node.py` (render + apply_edits + batch_context)
- `src/schemas/confirmation_schema.py` (`ItemEdit` shape)
- `src/schemas/estimation_schema.py` (`MacroEstimation` adds `amount_g_estimated`)
- `prompts/confirmation_parser.md` (LLM prompt — confirmation parser)
- `prompts/macro_estimation.md` (LLM prompt — off-menu macro estimation)
- `src/i18n/__init__.py` + `src/i18n/en.yaml` + `src/i18n/he.yaml` (32 new keys total)
- `tests/unit/test_confirmation_node.py` (extended)
- `tests/unit/test_calculate_macros_node.py` (extended for the estimation-path natural-unit cases)

**Dependencies**: None new. Stdlib + existing project deps.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: YOU MUST READ THESE BEFORE IMPLEMENTING

- `src/agents/state.py` (lines 108-130) — `MacroResult` TypedDict; we add 2 fields here.
- `src/agents/nodes/calculate_macros_node.py` (lines 27-110) — `calculate_macros_node`. Both DB path (line 48-88) and estimation path (line 89-96) build the `MacroResult` dict. Both need the new fields. **Estimation path also needs the `(count, unit)` pass-through fix.**
- `src/agents/nodes/calculate_macros_node.py` (lines 113-145) — `_estimate_macros` helper for the estimation branch. Signature changes from `(food_name, amount_g, original_text)` to `(food_name, count, unit, original_text)`. Returns a `MacroResult` whose `amount_g` comes from the LLM's `amount_g_estimated`.
- `src/schemas/estimation_schema.py` — `MacroEstimation` Pydantic schema. We add a required `amount_g_estimated: float` field so the LLM explicitly states the gram amount it computed macros for. No more inferring from `count × default_unit_weight_g`.
- `prompts/macro_estimation.md` — LLM prompt for off-menu macro estimation. Today says *"You will receive the food name and an amount in grams"*. We change it to accept `(food_name, count, unit)` and require the LLM to compute `amount_g_estimated` and emit macros for that exact total.
- `tests/unit/test_calculate_macros_node.py` — has `TestCalculateMacrosDBPath` and (likely) `TestCalculateMacrosEstimationPath`. Helper `_macros_return` mirrors the tool's return shape; we'll need a similar `_estimate_return` for the new estimation flow. Tests for both grams and natural-unit estimation paths get added.
- `src/agents/nodes/confirmation_node.py` (lines 31-79) — `_format_batch_preview`. After PR #28 lands, this already accepts `consumed_at`. Render rule for natural units lives here.
- `src/agents/nodes/confirmation_node.py` (lines 80-150) — `confirmation_node` body; the loop. no changes to the loop body — only `_apply_edits` updates.
- `src/agents/nodes/confirmation_node.py` (lines 152-172) — `_parse_confirmation`. The `batch_context` line is built here (line 158-160). Task 18 updates this string.
- `src/agents/nodes/confirmation_node.py` (lines 174-220) — `_apply_edits`. Both DB branch (line 197-208) and estimated branch (line 210-218) need updating in tasks 14-15.
- `src/schemas/confirmation_schema.py` — `ItemEdit` class (line 6-17). Task 13 replaces `new_amount_g` with `(new_count, new_unit)`.
- `src/schemas/input_schema.py` (lines 22-27) — `SingleFoodItem.unit` Literal: `g | piece | slice | scoop | bottle | cup | tbsp | tsp | can`. Mirror this set on `ItemEdit.new_unit`.
- `src/services/food_service.py` (lines 31-47) — `resolve_amount_g`: the gram-conversion helper. Strict — raises `ValueError` if unit doesn't match `default_unit`. Mirror this logic in `_apply_edits` estimated branch.
- `src/services/food_service.py` (lines 285-311) — `calculate_food_macros` tool. Already accepts `(count, unit)` and returns `{"error": "..."}` on unit mismatch. DB-item edit branch passes through cleanly.
- `prompts/confirmation_parser.md` (whole file, ~20 lines) — current rules for confirm/reject/edit + grams-only edit instruction. Task 17 rewrites the edit rules.
- `src/i18n/__init__.py` (lines 33-67) — `Messages` TypedDict. **Parity check at import time refuses to boot on drift between TypedDict and YAMLs.** Adding keys requires updating all three files atomically.
- `src/i18n/en.yaml` and `src/i18n/he.yaml` — existing confirmation keys around lines 35-50. Mirror placement for new unit-label keys.
- `tests/unit/test_confirmation_node.py` — `SAMPLE_BATCH` constant (lines 23-60), `TestFormatBatchPreview` class, `TestConfirmationNodeEdit::test_edit_loops_and_re_shows` (uses `ItemEdit(new_amount_g=...)` on line 227 — must update for the new schema in task 13).

### Key precedent worth re-reading

`docs/plans/hitl-preview-show-consumed-at.md` (Fix #5, just landed via PR #28). Same area of code, same i18n pattern, same testing structure. The render-side test class (`TestFormatBatchPreview`) is already extended; we extend it again here.

### New Files to Create

None — all changes are edits to existing files.

### Relevant Documentation — read before implementing

- LangGraph state checkpointing: same as Fix #5. State serializes through JSON; `MacroResult` is a TypedDict so Python doesn't enforce shape at runtime. We're adding required fields and using direct access (`item["original_unit"]`); see `## NOTES` below for the in-flight checkpoint analysis.
- Pydantic v2 `Literal` field types: `ItemEdit.new_unit` mirrors `SingleFoodItem.unit`. Keep the Literal value list verbatim.
- `with_structured_output(ConfirmationResponse)` — when the schema changes, the LLM's emitted JSON shape changes too. The prompt needs to be updated in lockstep with the schema or the eval will tank.

### Patterns to Follow

**i18n key ordering** (mirror `src/i18n/__init__.py` style):

```python
# HITL unit labels (bot-rendered in preview when original_unit != "g")
confirmation_unit_label_piece_singular: str
confirmation_unit_label_piece_plural: str
# ... 8 units × 2 forms = 16 keys
```

Keep keys sorted by unit (alphabetical: bottle, can, cup, piece, scoop, slice, tbsp, tsp), with singular before plural for each. `"g"` doesn't get a key — the existing `Xg` rendering handles grams.

**Singular/plural picker** (one-line helper inside `_format_batch_preview`):

```python
def _unit_label_key(unit: str, count: float) -> str:
    suffix = "singular" if count == 1 else "plural"
    return f"confirmation_unit_label_{unit}_{suffix}"
```

Hebrew uses gendered/inflected plurals; for POC accept ungendered plural forms (e.g., `"פרוסות"` for slices, neutral). Don't try to gender-agree with food names — overkill.

**Render rule** (in `_format_batch_preview`):

```python
if item["original_unit"] == "g":
    description = f"{name} — {item['amount_g']}g{source_tag}"
else:
    label_key = _unit_label_key(item["original_unit"], item["original_count"])
    label = MESSAGES[label_key]
    description = f"{name} — {item['original_count']} {label} ({item['amount_g']}g){source_tag}"
```

**Estimated-edit conversion** (in `_apply_edits`):

```python
if new_unit == "g":
    new_grams = new_count
elif (
    new_unit == item.get("default_unit")
    and item.get("default_unit_weight_g")
):
    new_grams = new_count * item["default_unit_weight_g"]
else:
    # Surface clean error to user — don't crash the loop.
    # Add to processing_results so response_node can apologize.
    ...
    continue
```

**Prompt rule for unit inheritance** (in `prompts/confirmation_parser.md`):

> *"For `change_amount` edits, always emit both `new_count` and `new_unit`. If the user gave grams (e.g., '100 grams'), set `new_unit='g'`. If the user gave a natural unit (e.g., '3 slices'), set `new_unit` to that unit. **If the user gave only a count without a unit (e.g., 'תעשה 3', 'make it 3'), inherit `new_unit` from the item's `original_unit` shown in the batch context.** Never guess; always pull from the batch context."*

**Test fixture pattern**: extend `SAMPLE_BATCH` in `tests/unit/test_confirmation_node.py` so each item has `original_count` + `original_unit` keys. The existing 5 tests will still pass because they don't assert on description — only the new tests do.

---

## IMPLEMENTATION PLAN

All tasks below execute in a single linear sequence. Commit shape is decided post-execution via the `/commit` skill — natural break point (if splitting) is between task 12 (last render-side task) and task 13 (first edit-side task), but the plan does not prescribe one.

#### 1. UPDATE `src/agents/state.py`

- **IMPLEMENT**: Add 2 required fields to `MacroResult` TypedDict at the bottom of the existing field block:
  ```python
  original_count: float
  original_unit: str
  ```
- **PATTERN**: Mirror the existing `MacroResult` style (no Optional, plain types).
- **IMPORTS**: None new.
- **GOTCHA**: TypedDict doesn't enforce required fields at runtime (Python). The "required" semantics here are documentary; runtime safety comes from us populating them in `calculate_macros_node` for every code path that creates a `MacroResult`.
- **VALIDATE**: `uv run python -c "from src.agents.state import MacroResult; print(MacroResult.__annotations__['original_unit'])"` → prints `<class 'str'>`.

#### 2. UPDATE `src/schemas/estimation_schema.py` — add `amount_g_estimated`

- **IMPLEMENT**: Add a new required field to `MacroEstimation`, placed near the existing macro fields:
  ```python
  amount_g_estimated: float = Field(
      ...,
      description=(
          "The total gram amount you used to compute the macros below. "
          "If the input unit was 'g', this equals the input count. "
          "If the input unit was a natural unit (slice, piece, cup, etc.), "
          "this MUST equal count × default_unit_weight_g (i.e., the gram total "
          "for the user's stated quantity). Macros must be for THIS gram amount."
      ),
  )
  ```
- **PATTERN**: Mirror existing `MacroEstimation` field style (Field with `...` for required + description).
- **IMPORTS**: None new (`Field` already imported).
- **GOTCHA**:
  - **Required** field (`...`), not `Optional`. The whole point is to remove inference — the LLM must state the gram amount explicitly so we can use it directly.
  - This is a breaking change to the LLM's emitted JSON schema. Stale prompt cache will fail. The prompt update in task 3 + the call-site update in task 5 land together.
- **VALIDATE**: `uv run python -c "from src.schemas.estimation_schema import MacroEstimation; print(MacroEstimation.model_fields['amount_g_estimated'])"` → prints field info with `required=True`.

#### 3. UPDATE `prompts/macro_estimation.md` — accept `(count, unit)`, emit `amount_g_estimated`

- **IMPLEMENT**:
  - Replace the `## Inputs` section:
    ```markdown
    ## Inputs
    You will receive: the food name (in the user's original language), a quantity `count`, and a `unit` from the set
    (`g | piece | slice | scoop | bottle | cup | tbsp | tsp | can`). The `count + unit` is the user's stated quantity.
    ```
  - Replace the `### 1. Macros (required)` section:
    ```markdown
    ### 1. Macros + amount (required)

    First decide the **total gram amount** the user is logging:
    - If `unit == "g"`: `amount_g_estimated = count` (the user already gave you grams).
    - If `unit` is a natural unit: estimate `default_unit_weight_g` for ONE of that unit (per Section 6 below),
      then set `amount_g_estimated = count × default_unit_weight_g`. Round to a whole gram.

    Then estimate `calories`, `protein`, `carbs`, `fat` for that **exact gram total** (not per-100g, not per-unit).
    Round all macro values to 1 decimal place.

    Worked example — input `count=2, unit="slice", food_name="פיצה"`:
    - default_unit_weight_g = 100 (one slice ≈ 100g)
    - amount_g_estimated = 2 × 100 = 200
    - calories = ~540, protein = ~22, carbs = ~60, fat = ~22 (for 200g pizza)

    Worked example — input `count=300, unit="g", food_name="pizza"`:
    - amount_g_estimated = 300 (input was grams)
    - calories = ~810, protein = ~33, carbs = ~90, fat = ~33 (for 300g pizza)
    - default_unit / default_unit_weight_g per Sections 5-6 below regardless.

    Use standard USDA / nutrition reference values when available. If the food name is ambiguous, assume the most common variety.
    ```
  - Update Section 6 (`Default unit weight`) to remove the "Emit null when default_unit is null" rule for the natural-unit input case — when input unit is natural, both `default_unit` AND `default_unit_weight_g` MUST be set (consistent with the gram math above):
    ```markdown
    ### 6. Default unit weight (required when input unit is natural; otherwise paired with `default_unit`)

    When the input `unit` is natural (slice/piece/cup/etc.), you MUST emit both `default_unit` and `default_unit_weight_g`,
    and `default_unit_weight_g` must be consistent with `amount_g_estimated`:
    `amount_g_estimated == count × default_unit_weight_g`.

    When the input `unit == "g"` and the food has an obvious natural unit (e.g., "pizza" — gram-input, but slice is natural),
    emit `default_unit` and `default_unit_weight_g` so future logs of "1 slice of pizza" can resolve correctly.

    When the input `unit == "g"` and the food is gram-native in everyday speech (rice, sauce, soup), emit null for both.

    Reference weights:
    - one whole egg → ~50g
    - one slice of bread → ~30g
    - one slice of pizza → ~100g
    - one scoop of whey → ~32g
    - one bottle of beer → 330g
    - one medium banana → ~120g
    ```
- **PATTERN**: Mirror the existing prompt's structure — keep section numbering, add explicit worked examples (the Plan 3 prompts already use this style).
- **IMPORTS**: N/A (Markdown).
- **GOTCHA**:
  - The math constraint `amount_g_estimated == count × default_unit_weight_g` for natural-unit input is critical. If the LLM violates it (says "200g pizza but 50g per slice"), the data is internally inconsistent. Eval should catch this.
  - The phrase "for that **exact gram total**" must be unmissable — without it, the LLM may revert to per-100g macros. Bold it in the prompt.
- **VALIDATE**: covered by task 6 below (estimation path tests).

#### 4. UPDATE `src/agents/nodes/calculate_macros_node.py` — DB path

- **IMPLEMENT**: In the DB branch (the dict literal starting around line 71), add two keys:
  ```python
  "original_count": count,
  "original_unit": unit,
  ```
  `count` and `unit` are already extracted from `current_item` at the top of the function (lines 44-45).
- **PATTERN**: Mirror the existing key ordering — group near `original_text` since they're "what the user said" companion fields.
- **IMPORTS**: None new.
- **GOTCHA**: Don't pull from `pending_items[0]` again — use the locals `count` and `unit` already in scope. Avoids a second dict read.
- **VALIDATE**: covered by task 6 (test_confirmation_node SAMPLE_BATCH update) + task 7 (estimation path tests).

#### 5. UPDATE `src/agents/nodes/calculate_macros_node.py` — estimation path (`_estimate_macros`)

- **IMPLEMENT**:
  - Change `_estimate_macros` signature from `(food_name, amount_g, original_text)` to `(food_name, count, unit, original_text)`.
  - Update the system/user message to pass `(count, unit, food_name)`:
    ```python
    messages = [
        SystemMessage(content=_ESTIMATION_PROMPT),
        HumanMessage(
            content=f"Estimate macros for: {food_name}, quantity: {count} {unit}"
        ),
    ]
    result = await structured_llm.ainvoke(messages)
    ```
  - Use the LLM's `amount_g_estimated` directly:
    ```python
    return {
        "name_en": result.name_en,
        "name_he": result.name_he,
        "amount_g": result.amount_g_estimated,  # ← was the input arg; now from LLM
        "calories": round(result.calories, 1),
        "protein": round(result.protein, 1),
        "carbs": round(result.carbs, 1),
        "fat": round(result.fat, 1),
        "source": "estimated",
        "category": result.category,
        "tag": result.tag,
        "serving_amount_g": None,
        "servings": None,
        "default_unit": result.default_unit,
        "default_unit_weight_g": result.default_unit_weight_g,
        "original_text": original_text,
        "food_id": None,
        "original_count": count,    # ← user's actual count
        "original_unit": unit,      # ← user's actual unit
    }
    ```
  - Update the call site in `calculate_macros_node` (around line 89-96) — drop the `amount_g = count` line; pass `(count, unit)` directly:
    ```python
    else:
        # Estimation path — pass the user's (count, unit) through to the LLM,
        # which is responsible for computing amount_g_estimated and macros for
        # that exact total. Fixes the previous bug where unit was collapsed
        # to grams and "2 slices" got estimated as 2 grams.
        logger.info(
            "Estimating macros via LLM",
            food=food_name, count=count, unit=unit,
        )
        macro_result = await _estimate_macros(
            food_name, count, unit, current_item.get("original_text", "")
        )
    ```
- **PATTERN**: Mirror the DB-path call site that uses `current_item`'s `count` + `unit` directly without intermediate variables.
- **IMPORTS**: None new.
- **GOTCHA**:
  - Removing the `amount_g = count` line is the core fix. Don't keep both code paths; remove the old one.
  - The LLM must populate `amount_g_estimated` correctly per the prompt. If it doesn't (parsing succeeds but value is wrong), Pydantic accepts it — the error surfaces only via dev-bot smoke or eval. This is the load-bearing trust point in Option C.
  - `default_unit_weight_g` and `default_unit` may now be set even on grams input (per the updated prompt Section 6). That's fine — they're still optional on `MacroResult`.
- **VALIDATE**: covered by task 7.

#### 6. UPDATE `tests/unit/test_confirmation_node.py` — extend `SAMPLE_BATCH`

- **IMPLEMENT**: Add `"original_count": ...` and `"original_unit": ...` to each of the 2 items in `SAMPLE_BATCH`:
  - chicken (DB, `"original_text": "200g chicken"`): `"original_count": 200, "original_unit": "g"`
  - pizza (estimated, `"original_text": "3 slices of pizza"`): `"original_count": 3, "original_unit": "slice"` (estimation now preserves the user's unit per tasks 3 + 5)
- **PATTERN**: Match existing `SAMPLE_BATCH` field ordering — put new fields adjacent to `original_text`.
- **IMPORTS**: None new.
- **GOTCHA**: The existing `TestConfirmationNodeEdit::test_edit_loops_and_re_shows` (line 196-268) has its own inline batch fixture (lines 196-213). **Update that fixture too** — same field additions. Easy to miss because it shadows `SAMPLE_BATCH`.
- **VALIDATE**: `uv run pytest tests/unit/test_confirmation_node.py -v` → all 12 existing tests still pass.

#### 7. UPDATE `tests/unit/test_calculate_macros_node.py` — add estimation-path natural-unit tests

- **IMPLEMENT**:
  - Add a helper `_estimate_return(...)` mirroring `_macros_return` but for the `MacroEstimation`-shaped LLM mock return:
    ```python
    def _estimate_return(
        *,
        name_en="Pizza",
        name_he="פיצה",
        amount_g_estimated=200.0,
        calories=540.0,
        protein=22.0,
        carbs=60.0,
        fat=22.0,
        category=None,
        tag=None,
        default_unit="slice",
        default_unit_weight_g=100.0,
    ):
        return MagicMock(
            name_en=name_en, name_he=name_he,
            amount_g_estimated=amount_g_estimated,
            calories=calories, protein=protein, carbs=carbs, fat=fat,
            category=category, tag=tag,
            default_unit=default_unit, default_unit_weight_g=default_unit_weight_g,
        )
    ```
  - Extend `TestCalculateMacrosEstimationPath` (or add the class if missing) with three new tests:
    ```python
    async def test_estimation_grams_input_passes_count_through(self, basic_state):
        """
        arrange: pending_food_items=[{count:300, unit:"g", food_name:"pizza"}],
                 selected_food_id=None; mock LLM returns amount_g_estimated=300.
        act:     run calculate_macros_node.
        assert:  resulting MacroResult has amount_g=300, original_count=300,
                 original_unit="g".
        """

    async def test_estimation_natural_unit_uses_llm_amount_g(self, basic_state):
        """
        arrange: pending_food_items=[{count:2, unit:"slice", food_name:"pizza"}],
                 selected_food_id=None; mock LLM returns amount_g_estimated=200,
                 default_unit_weight_g=100, calories=540.
        act:     run calculate_macros_node.
        assert:  MacroResult has amount_g=200 (from LLM, not 2g), original_count=2,
                 original_unit="slice", calories=540.
        """

    async def test_estimation_call_passes_count_and_unit_in_human_message(self, basic_state):
        """
        arrange: pending_food_items=[{count:2, unit:"slice", food_name:"pizza"}].
        act:     run calculate_macros_node, capture LLM invocation messages.
        assert:  HumanMessage content contains "2 slice" and "pizza".
        """
    ```
  - Mock the LLM via `patch("src.agents.nodes.calculate_macros_node.get_llm_for_node")` returning a MagicMock with `with_structured_output(...).ainvoke = AsyncMock(return_value=_estimate_return(...))`.
- **PATTERN**: Mirror existing DB-path tests in the same file. Use `_estimate_return` for the LLM-mock return shape, parallel to `_macros_return` for the tool mock.
- **IMPORTS**: `from unittest.mock import patch, AsyncMock, MagicMock` (likely already in scope).
- **GOTCHA**:
  - The LLM mock needs `with_structured_output(MacroEstimation)` chained — verify against the existing estimation-path test pattern in this file if one exists, or use:
    ```python
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_structured.ainvoke = AsyncMock(return_value=_estimate_return(...))
    mock_llm.with_structured_output.return_value = mock_structured
    ```
  - The third test (capture messages) is a defensive check that we actually pass `count` and `unit` into the prompt — easy to forget after refactoring.
- **VALIDATE**: `uv run pytest tests/unit/test_calculate_macros_node.py -v` → all tests green.

#### 8. UPDATE `src/i18n/__init__.py` — add 16 unit-label keys to `Messages` TypedDict

- **IMPLEMENT**: Add a new commented section after the existing HITL keys:
  ```python
  # HITL unit labels (bot-rendered in preview when original_unit != "g")
  confirmation_unit_label_bottle_singular: str
  confirmation_unit_label_bottle_plural: str
  confirmation_unit_label_can_singular: str
  confirmation_unit_label_can_plural: str
  confirmation_unit_label_cup_singular: str
  confirmation_unit_label_cup_plural: str
  confirmation_unit_label_piece_singular: str
  confirmation_unit_label_piece_plural: str
  confirmation_unit_label_scoop_singular: str
  confirmation_unit_label_scoop_plural: str
  confirmation_unit_label_slice_singular: str
  confirmation_unit_label_slice_plural: str
  confirmation_unit_label_tbsp_singular: str
  confirmation_unit_label_tbsp_plural: str
  confirmation_unit_label_tsp_singular: str
  confirmation_unit_label_tsp_plural: str
  ```
- **PATTERN**: Mirror existing TypedDict style; group with a section comment.
- **IMPORTS**: None.
- **GOTCHA**: No `g` keys — grams are rendered via the existing `Xg` suffix rule, not via a unit label. Don't add `confirmation_unit_label_g_*`.
- **VALIDATE**: After this task alone the import will fail with the parity error (YAMLs missing the keys). Expected.

#### 9. UPDATE `src/i18n/en.yaml` — add 16 EN values

- **IMPLEMENT**: Add a new section after `confirmation_category_label_forbidden_main`:
  ```yaml
  # --- HITL unit labels (bot-rendered in preview when original_unit != "g") ---
  confirmation_unit_label_bottle_singular: "bottle"
  confirmation_unit_label_bottle_plural: "bottles"
  confirmation_unit_label_can_singular: "can"
  confirmation_unit_label_can_plural: "cans"
  confirmation_unit_label_cup_singular: "cup"
  confirmation_unit_label_cup_plural: "cups"
  confirmation_unit_label_piece_singular: "piece"
  confirmation_unit_label_piece_plural: "pieces"
  confirmation_unit_label_scoop_singular: "scoop"
  confirmation_unit_label_scoop_plural: "scoops"
  confirmation_unit_label_slice_singular: "slice"
  confirmation_unit_label_slice_plural: "slices"
  confirmation_unit_label_tbsp_singular: "tbsp"
  confirmation_unit_label_tbsp_plural: "tbsp"
  confirmation_unit_label_tsp_singular: "tsp"
  confirmation_unit_label_tsp_plural: "tsp"
  ```
- **PATTERN**: Mirror existing YAML style (alphabetical by unit, singular before plural).
- **IMPORTS**: N/A.
- **GOTCHA**: `tbsp` and `tsp` don't pluralize in normal English usage ("3 tbsp", not "3 tbsps") — keep both forms identical for those two units.
- **VALIDATE**: After this task `MESSAGES` import will still fail (he.yaml missing). Don't run validate yet.

#### 10. UPDATE `src/i18n/he.yaml` — add 16 HE values

- **IMPLEMENT**: Mirror EN section with Hebrew translations:
  ```yaml
  # --- HITL unit labels (bot-rendered in preview when original_unit != "g") ---
  confirmation_unit_label_bottle_singular: "בקבוק"
  confirmation_unit_label_bottle_plural: "בקבוקים"
  confirmation_unit_label_can_singular: "פחית"
  confirmation_unit_label_can_plural: "פחיות"
  confirmation_unit_label_cup_singular: "כוס"
  confirmation_unit_label_cup_plural: "כוסות"
  confirmation_unit_label_piece_singular: "יחידה"
  confirmation_unit_label_piece_plural: "יחידות"
  confirmation_unit_label_scoop_singular: "כף"
  confirmation_unit_label_scoop_plural: "כפות"
  confirmation_unit_label_slice_singular: "פרוסה"
  confirmation_unit_label_slice_plural: "פרוסות"
  confirmation_unit_label_tbsp_singular: "כף"
  confirmation_unit_label_tbsp_plural: "כפות"
  confirmation_unit_label_tsp_singular: "כפית"
  confirmation_unit_label_tsp_plural: "כפיות"
  ```
- **PATTERN**: Standard Hebrew plural forms (mostly -ות / -ים endings).
- **IMPORTS**: N/A.
- **GOTCHA**: `scoop` and `tbsp` both translate to "כף/כפות" — that's fine. `tsp` gets "כפית/כפיות" (smaller). The user will see whichever the input parser routed into `original_unit`, so the difference matters per-food (a protein scoop is "כף", a teaspoon of cinnamon is "כפית").
- **VALIDATE**:
  - `uv run python -c "from src.i18n import MESSAGES; print(MESSAGES['confirmation_unit_label_slice_plural'])"` → `slices` (en default).
  - `BOT_LANGUAGE=he uv run python -c "from src.i18n import MESSAGES; print(MESSAGES['confirmation_unit_label_slice_plural'])"` → `פרוסות`.

#### 11. UPDATE `src/agents/nodes/confirmation_node.py` — render rule

- **IMPLEMENT**:
  - Add a small helper above `_format_batch_preview`:
    ```python
    def _unit_label_key(unit: str, count: float) -> str:
        suffix = "singular" if count == 1 else "plural"
        return f"confirmation_unit_label_{unit}_{suffix}"
    ```
  - Update the per-item description build inside `_format_batch_preview` (around line 50). Replace:
    ```python
    "description": f"{name} — {item['amount_g']}g{source_tag}",
    ```
    with:
    ```python
    if item["original_unit"] == "g":
        description = f"{name} — {item['amount_g']}g{source_tag}"
    else:
        label = MESSAGES[_unit_label_key(item["original_unit"], item["original_count"])]
        description = (
            f"{name} — {item['original_count']} {label} ({item['amount_g']}g){source_tag}"
        )
    formatted_items.append(
        {
            "index": i,
            "description": description,
            ...
        }
    )
    ```
- **PATTERN**: Helper function above the public API; mirror Fix #5's `_format_date_label` placement.
- **IMPORTS**: None new.
- **GOTCHA**:
  - The number `1` for singular check should be exact (`count == 1`). Counts like `1.5` go to plural (Hebrew convention: non-integer ≠ singular). Counts like `0.5` also go to plural.
  - `original_count` may be a float like `2.0`. The render `f"{count}"` produces `"2.0"` — ugly. Cast to int when whole: use `int(count) if count == int(count) else count` or simpler `f"{count:g}"` (general format strips trailing zeros). Recommend `f"{count:g}"`.
- **VALIDATE**: covered by task 12.

#### 12. UPDATE `tests/unit/test_confirmation_node.py` — extend `TestFormatBatchPreview`

- **IMPLEMENT**: Add three new tests:
  ```python
  def test_grams_renders_as_xg(self):
      """
      arrange: SAMPLE_BATCH item with original_unit="g".
      act:     format batch preview.
      assert:  description is "{name} — {amount_g}g" (no unit label).
      """
      preview = _format_batch_preview(SAMPLE_BATCH)
      assert "200" in preview["items"][0]["description"]
      assert "g" in preview["items"][0]["description"]
      # No "slice" / "piece" etc.
      assert "slice" not in preview["items"][0]["description"]

  def test_natural_unit_renders_with_label_and_grams(self, monkeypatch):
      """
      arrange: batch with item original_count=2, original_unit="slice".
      act:     format batch preview in EN.
      assert:  description contains "2 slices (50g)".
      """
      monkeypatch.setenv("BOT_LANGUAGE", "en")
      batch = [
          {**SAMPLE_BATCH[0], "amount_g": 50, "original_count": 2, "original_unit": "slice"},
      ]
      preview = _format_batch_preview(batch)
      assert "2 slices" in preview["items"][0]["description"]
      assert "(50" in preview["items"][0]["description"]

  def test_natural_unit_singular_form_for_count_one(self, monkeypatch):
      """
      arrange: batch with item original_count=1, original_unit="slice".
      act:     format batch preview in EN.
      assert:  description contains "1 slice" (singular), not "slices".
      """
      monkeypatch.setenv("BOT_LANGUAGE", "en")
      batch = [
          {**SAMPLE_BATCH[0], "amount_g": 25, "original_count": 1, "original_unit": "slice"},
      ]
      preview = _format_batch_preview(batch)
      assert "1 slice" in preview["items"][0]["description"]
      assert "1 slices" not in preview["items"][0]["description"]
  ```
  Plus reload the i18n module if needed when `BOT_LANGUAGE` changes during the test (existing tests already do this — mirror).
- **PATTERN**: Mirror existing `TestFormatBatchPreview` tests; AAA docstring.
- **IMPORTS**: None new beyond what's already in the file.
- **GOTCHA**: `monkeypatch.setenv("BOT_LANGUAGE", "en")` only affects new module imports. The `MESSAGES` constant was loaded at first import. Existing tests handle this by relying on the default being `en`. If the test order causes `BOT_LANGUAGE=he` to leak from a prior test, results will be Hebrew. Use the existing test pattern (no env reset needed if tests start clean).
- **VALIDATE**: `uv run pytest tests/unit/test_confirmation_node.py -v` → all 15 tests pass (12 existing + 3 new).

> **Inter-phase note** — task 12 is the last task that doesn't change the parser's prompt or `ItemEdit` schema. If splitting commits, this is the natural break point: tasks 1-12 ship the render side + estimation-path fix; tasks 13-19 ship the edit-grammar side. Both share the new `original_count`/`original_unit` fields.

#### 13. UPDATE `src/schemas/confirmation_schema.py` — replace `new_amount_g` with `(new_count, new_unit)`

- **IMPLEMENT**:
  ```python
  from typing import List, Literal, Optional
  from pydantic import BaseModel, Field


  class ItemEdit(BaseModel):
      """A single edit to apply to a batch item."""

      item_index: int = Field(
          ..., description="0-based index of the item in the batch to edit"
      )
      edit_type: Literal["change_amount", "remove"] = Field(
          ..., description="Type of edit"
      )
      new_count: Optional[float] = Field(
          None,
          description=(
              "New quantity in the unit specified by new_unit (only for change_amount). "
              "For grams, new_unit must be 'g'."
          ),
      )
      new_unit: Optional[
          Literal["g", "piece", "slice", "scoop", "bottle", "cup", "tbsp", "tsp", "can"]
      ] = Field(
          None,
          description=(
              "Unit for new_count (only for change_amount). 'g' for grams; "
              "natural units otherwise. If the user gave only a count without a unit, "
              "inherit from the item's original_unit shown in the batch context."
          ),
      )
  ```
- **PATTERN**: Mirror `SingleFoodItem.unit` Literal verbatim — they must stay in sync. (If we ever extend the unit set, both schemas update together.)
- **IMPORTS**: Already present.
- **GOTCHA**:
  - **Removing `new_amount_g` is a breaking change to the JSON Schema the LLM emits.** This is intentional. The prompt update in task 17 teaches the new shape.
  - The `Literal` value list must be a tuple/list of strings, not a separate `enum`. Pydantic v2 generates JSON Schema enum from Literal automatically.
- **VALIDATE**: `uv run python -c "from src.schemas.confirmation_schema import ItemEdit; print(ItemEdit.model_fields['new_unit'].annotation)"` → prints the Literal type.

#### 14. UPDATE `src/agents/nodes/confirmation_node.py` — `_apply_edits` DB branch

- **IMPLEMENT**: In `_apply_edits`, the DB-item path (currently checks `item["food_id"] is not None`):
  ```python
  if item["food_id"] is not None:
      macros = await calculate_food_macros.ainvoke(
          {"food_id": item["food_id"], "count": edit.new_count, "unit": edit.new_unit}
      )
      if "error" not in macros:
          item["amount_g"] = macros["amount_g"]
          item["calories"] = macros["calories"]
          item["protein"] = macros["protein"]
          item["carbs"] = macros["carbs"]
          item["fat"] = macros["fat"]
          item["servings"] = macros.get("servings")  # may have changed if count crossed serving boundary
          item["original_count"] = edit.new_count
          item["original_unit"] = edit.new_unit
      else:
          # Surface the error to the user via processing_results
          # ... see task 16 for shared error-surfacing
          ...
  ```
- **PATTERN**: Mirror the existing fresh-log path in `calculate_macros_node` — same tool, same args, same error shape. We're literally re-running the calc.
- **IMPORTS**: None new.
- **GOTCHA**:
  - Don't forget to update `servings` — if the user changes "200g chicken" (= 2 servings) to "1 piece" (= different gram amount), the servings count changes. The tool returns the new value; just propagate.
  - If `calculate_food_macros` returns `{"error": ...}` (e.g., unit mismatch on the DB row's allowed units), don't update the item. Surface the error — see task 16.
- **VALIDATE**: covered by task 19 (the updated edit-loops test).

#### 15. UPDATE `src/agents/nodes/confirmation_node.py` — `_apply_edits` estimated branch

- **IMPLEMENT**: Replace the existing estimated branch (currently around line 210-218) with:
  ```python
  else:
      # Estimated item — no food_id, no DB row. Convert to grams using the item's
      # default_unit_weight_g when the user gave a non-grams unit.
      if edit.new_unit == "g":
          new_grams = edit.new_count
      elif (
          edit.new_unit == item.get("default_unit")
          and item.get("default_unit_weight_g")
      ):
          new_grams = edit.new_count * item["default_unit_weight_g"]
      else:
          # Unit mismatch we can't convert — surface clean error, don't crash.
          # User can re-issue the edit in grams or in the supported unit.
          # ... see task 16 for shared error-surfacing
          ...
          continue

      if item["amount_g"] > 0:
          ratio = new_grams / item["amount_g"]
          item["amount_g"] = new_grams
          item["calories"] = round(item["calories"] * ratio, 1)
          item["protein"] = round(item["protein"] * ratio, 1)
          item["carbs"] = round(item["carbs"] * ratio, 1)
          item["fat"] = round(item["fat"] * ratio, 1)
          item["original_count"] = edit.new_count
          item["original_unit"] = edit.new_unit
  ```
- **PATTERN**: Mirror `resolve_amount_g` in `food_service.py:31-47` for the unit-conversion logic, but inlined (no `FoodItem` row to pass).
- **IMPORTS**: None new.
- **GOTCHA**:
  - `item.get("default_unit_weight_g")` may be `None` (some estimated items don't have a weight populated). Treat `None` as "can't convert" and fall through to the error path.
  - The `continue` statement ends *this edit* and moves to the next edit in the loop — it does NOT skip applying other edits. Critical that we don't `break` the whole loop on one mismatch.
- **VALIDATE**: covered by task 19.

#### 16. UPDATE `src/agents/nodes/confirmation_node.py` — error-surfacing for unit mismatches

- **IMPLEMENT**: Add a helper for both branches in tasks 14 + 15 to produce a clean processing_result on error:
  ```python
  def _surface_edit_error(
      item: MacroResult,
      edit: ItemEdit,
      message: str,
  ) -> ProcessingResult:
      """Build a FAILED ProcessingResult for a rejected unit-mismatch edit."""
      return {
          "food_name": item["name_en"],
          "name_he": item.get("name_he"),
          "count": edit.new_count or 0.0,
          "unit": edit.new_unit or "g",
          "original_text": item["original_text"],
          "status": "FAILED",
          "message": message,
          "source": item.get("source"),
      }
  ```
  Then in task 14 (DB error case):
  ```python
  state.setdefault("processing_results", []).append(
      _surface_edit_error(item, edit, macros["error"])
  )
  ```
  And in task 15 (estimated mismatch case):
  ```python
  state.setdefault("processing_results", []).append(
      _surface_edit_error(item, edit, f"Can only edit in grams or {item.get('default_unit')}")
  )
  ```
- **PATTERN**: Mirror the existing FAILED-result construction in `confirmation_node.py` (the reject path already builds these — line 113-127).
- **IMPORTS**: None new (`ProcessingResult` already imported via `MacroResult` line; if not, add `from src.agents.state import ProcessingResult`).
- **GOTCHA**:
  - **`_apply_edits` doesn't currently take `state`** — it's a pure function on `(batch, edits)`. To surface errors via `processing_results`, either (a) change the signature to accept `state` and mutate it, or (b) return a list of error results that the caller appends. Option (b) is cleaner — it keeps the function pure-ish.
  - Recommended signature change: `_apply_edits(batch, edits) -> tuple[list[MacroResult], list[ProcessingResult]]` — returns updated batch + any errors. Caller appends errors to state.
  - Update the call site in `confirmation_node` body (line 141) accordingly.
- **VALIDATE**: covered by task 19 + new tests added there.

#### 17. UPDATE `prompts/confirmation_parser.md` — emit `(new_count, new_unit)` + inheritance rule

- **IMPLEMENT**: Replace the current rules block:
  ```markdown
  ## Rules for edits
  1. `item_index` is 0-based, matching the order items were presented
  2. `change_amount` means the user wants a different quantity in grams
  3. `remove` means the user wants to drop that item entirely
  4. Parse amounts to grams (e.g., "150g" → 150.0)
  5. Match food names to the closest item in the batch by name
  ```
  with:
  ```markdown
  ## Rules for edits

  1. `item_index` is 0-based, matching the order items were presented.
  2. Match food names to the closest item in the batch by name.
  3. `remove` means the user wants to drop that item entirely. Don't emit `new_count`/`new_unit` for removes.
  4. `change_amount` means the user wants a different quantity. **Always emit both `new_count` and `new_unit`.**
     - Grams: user said "100 grams" / "100 גרם" → `new_count=100, new_unit="g"`.
     - Natural unit: user said "3 slices" / "3 פרוסות" → `new_count=3, new_unit="slice"`.
     - **Count-only (no unit stated)**: user said "תעשה 3" / "make it 3" → inherit `new_unit` from the item's `original_unit` shown in the batch context. Never guess; always read it from the batch.
  5. Supported `new_unit` values: `g`, `piece`, `slice`, `scoop`, `bottle`, `cup`, `tbsp`, `tsp`, `can`. If the user used a unit outside this set (e.g., "glass", "handful", "loaf"), pick the closest match — or fall back to `g` with an estimated count if the closest match is not obvious.

  ## Examples

  Item 0 in batch: `[0] גבינה — 2 slice (50g, database)` (original_unit="slice", original_count=2)

  - User: "תעשה 3 פרוסות" → `edits=[{item_index:0, edit_type:"change_amount", new_count:3, new_unit:"slice"}]`
  - User: "תעשה 100 גרם" → `edits=[{item_index:0, edit_type:"change_amount", new_count:100, new_unit:"g"}]`
  - User: "תעשה 3" (count-only) → `edits=[{item_index:0, edit_type:"change_amount", new_count:3, new_unit:"slice"}]` (inherit slice from batch context)
  - User: "תוריד את הגבינה" → `edits=[{item_index:0, edit_type:"remove"}]`

  Item 0: `[0] חזה עוף — 200 g (200g, database)` (original_unit="g", original_count=200)

  - User: "תעשה 150" (count-only on grams item) → `edits=[{item_index:0, edit_type:"change_amount", new_count:150, new_unit:"g"}]`
  ```
- **PATTERN**: Mirror existing prompt structure. Keep the file short — the prompt is loaded into every confirmation parse.
- **IMPORTS**: N/A (Markdown).
- **GOTCHA**:
  - The prompt previously said "Parse amounts to grams" — that rule is now wrong and must be removed, not merely supplemented.
  - The Examples section is critical for the LLM to learn the inheritance behavior. Don't skip it.
- **VALIDATE**: `uv run pytest notebooks/evals/eval_confirmation_parser.py` (or the eval entrypoint) — see task 21 (manual smoke).

#### 18. UPDATE `src/agents/nodes/confirmation_node.py` — `_parse_confirmation` batch_context

- **IMPLEMENT**: Replace the existing batch_context build (around line 158-160):
  ```python
  batch_context = "\n".join(
      f"[{i}] {item.get('name_he') or item['name_en']} — {item['amount_g']}g ({item['source']})"
      for i, item in enumerate(batch)
  )
  ```
  with:
  ```python
  batch_context = "\n".join(
      f"[{i}] {item.get('name_he') or item['name_en']} — "
      f"{item['original_count']:g} {item['original_unit']} "
      f"({item['amount_g']}g, {item['source']})"
      for i, item in enumerate(batch)
  )
  ```
- **PATTERN**: Mirror the render rule in `_format_batch_preview` (task 11) — same shape, less i18n. The LLM doesn't need localized labels; it works directly on the unit string.
- **IMPORTS**: None new.
- **GOTCHA**: `f"{count:g}"` strips trailing `.0` (so `2.0` renders as `2`). Matches the prompt's example syntax.
- **VALIDATE**: `uv run pytest tests/unit/test_confirmation_node.py -v` — existing tests don't assert on batch_context shape, so they should pass. The eval is the real validator.

#### 19. UPDATE `tests/unit/test_confirmation_node.py` — extend `TestConfirmationNodeEdit`

- **IMPLEMENT**: Update `test_edit_loops_and_re_shows` to use the new `ItemEdit(new_count=..., new_unit=...)` signature (line 227) and update the inline batch fixture (lines 196-213) with `original_count`/`original_unit` (already done in task 6). Add three new tests:
  ```python
  async def test_edit_natural_unit_db_item(self, basic_state):
      """
      arrange: state with batch holding a DB item original=slice; user edits to 3 slices.
      act:     run confirmation_node, mock interrupt to "תעשה 3 פרוסות" then "yes".
      assert:  calculate_food_macros tool called with (count=3, unit="slice");
               item's amount_g, original_count, original_unit reflect the new edit.
      """
      # ... mirror test_edit_loops_and_re_shows pattern with new edit shape

  async def test_edit_estimated_unit_conversion(self, basic_state):
      """
      arrange: estimated item with default_unit="slice", default_unit_weight_g=100;
               user edits "make it 3 slices".
      act:     run confirmation_node.
      assert:  amount_g = 3 * 100 = 300; macros scaled proportionally;
               original_count=3, original_unit="slice".
      """
      # ... batch with estimated pizza, default_unit_weight_g=100

  async def test_edit_estimated_unit_mismatch_surfaces_error(self, basic_state):
      """
      arrange: estimated item with default_unit="slice"; user edits "make it 1 cup".
      act:     run confirmation_node.
      assert:  item is unchanged; processing_results contains a FAILED entry
               with a message mentioning grams or the natural unit.
      """
  ```
- **PATTERN**: Mirror the existing `test_edit_loops_and_re_shows` mocking pattern (mock interrupt + mock parse_confirmation + mock calculate_food_macros).
- **IMPORTS**: Update `ItemEdit` constructor calls.
- **GOTCHA**:
  - The DB-item edit test's `mock_calc.ainvoke.assert_called_once_with({...})` assertion (line 266) currently asserts the old shape `{"food_id": ..., "count": ..., "unit": "g"}`. Update to `{"food_id": ..., "count": 3, "unit": "slice"}`.
  - For the unit-mismatch test, mock `_parse_confirmation` to return `ConfirmationResponse(action="edit", edits=[ItemEdit(item_index=0, edit_type="change_amount", new_count=1, new_unit="cup")])`. The test asserts `processing_results` has the FAILED entry, but since the loop continues to interrupt for confirm/reject, you'll need a second mock turn that returns "no" to exit. Or have the unit-mismatch path itself terminate (it doesn't — it continues editing).
- **VALIDATE**: `uv run pytest tests/unit/test_confirmation_node.py -v` → all tests green (existing + 3 new).

#### 20. RUN full unit + integration suites + lint

- **IMPLEMENT**:
  ```bash
  uv run ruff check src/ bot/ tests/
  uv run pytest tests/unit/ -v
  uv run pytest tests/integration/ -v
  ```
- **PATTERN**: Pre-commit gate per CLAUDE.md.
- **IMPORTS**: N/A.
- **GOTCHA**:
  - If `test_format_batch_preview` style tests fail with `KeyError: 'original_count'`, the `SAMPLE_BATCH` update from task 6 was incomplete or the inline fixture in `test_edit_loops_and_re_shows` was missed.
  - Integration tier exercises the actual `calculate_food_macros` tool against the test DB. If any integration test asserts on the old `ItemEdit.new_amount_g` shape, update it.
- **VALIDATE**: All green; ruff clean.

#### 21. DEV-BOT MANUAL SMOKE

- **IMPLEMENT**: Run `langgraph dev` + bot in polling mode (`POLLING_MODE=true uv run python -m bot.gateway`). Test all 5 flows in Hebrew:
  1. **Confirm**: log "100 גרם חזה עוף" → preview → "כן" → committed.
  2. **Reject**: log "100 גרם חזה עוף" → preview → "לא" → cancelled.
  3. **Grams edit**: log "100 גרם חזה עוף" → preview → "תעשה 150 גרם" → preview shows 150g → "כן".
  4. **Natural-unit edit**: log "2 פרוסות גבינה" → preview shows "2 פרוסות (50g)" → "תעשה 3 פרוסות" → preview shows "3 פרוסות (75g)" → "כן".
  5. **Count-only inheritance**: log "2 פרוסות גבינה" → preview → "תעשה 4" → preview shows "4 פרוסות (100g)" → "כן".

  Repeat 3-5 in English with `BOT_LANGUAGE=en`.
- **PATTERN**: Manual smoke checklist in PR description (mirror Fix #5).
- **IMPORTS**: N/A.
- **GOTCHA**: Bot needs restart after the i18n change (32 new keys). LangGraph dev hot-reloads the graph code.
- **VALIDATE**: All 5 flows produce the expected behavior in both languages.

### Post-execution (NOT part of this plan)

After all 21 tasks above are complete and validation passes, hand off to:
- `/commit` skill — packages the changes into one or more commits and pushes the branch. Title suggestion if single commit: `ux(hitl): natural-unit rendering + unit-aware edits + estimation-path fix`. If splitting at task 12: separate titles for render side vs edit side.
- `gh pr create` (or via `/commit` flow) — opens the PR with: 6-flows × 2-langs manual-smoke checklist, eval-deferred note, links to TASKS Important #4 + the run1-baseline handoff.

---

## TESTING STRATEGY

### Unit Tests

**Render side** — `tests/unit/test_confirmation_node.py::TestFormatBatchPreview` adds 3 cases:
- Grams item renders as `Xg` (regression check — current behavior preserved).
- Natural-unit item renders as `N <label> (Xg)` (plural form).
- Singular form on count == 1.

**Estimation path** — `tests/unit/test_calculate_macros_node.py::TestCalculateMacrosEstimationPath` adds 3 cases (per task 7):
- Grams input → `amount_g` matches input count, `original_count`/`original_unit` reflect grams.
- Natural-unit input → `amount_g` comes from LLM's `amount_g_estimated` (e.g., 200g for "2 slices pizza"), `original_count=2`, `original_unit="slice"`.
- Verifies the LLM is invoked with a HumanMessage that includes the count + unit (defensive — easy to forget after refactor).

**Edit side** — `tests/unit/test_confirmation_node.py::TestConfirmationNodeEdit` adds 3 cases:
- Natural-unit edit on DB item — tool called with `(count, unit)`, item updates correctly.
- Estimated-item unit conversion via `default_unit_weight_g` — gram conversion + proportional macro scaling.
- Estimated-item unit mismatch — surfaces FAILED ProcessingResult, item unchanged.

### Integration Tests

`tests/integration/` has DB-backed tool tests. They should pass without changes since `calculate_food_macros` already accepts `(count, unit)`. If any test asserts on the `ItemEdit.new_amount_g` field directly, update it. Run the suite to verify.

### Eval Tests

**Deferred to a follow-up PR** (separate session). Reasoning: building the eval *before* the new mechanic stabilizes means churning reference outputs through implementation. Building it *after* this PR lets it lock in the intended final shape and act as a durable regression guard for future changes.

For THIS PR, the safety net is unit tests (~9 new) + integration tier + dev-bot manual smoke (6 flows × 2 langs).

Add to brain TASKS.md as a follow-up: see top-of-plan callout for the dataset shape + evaluator list.

### Manual Smoke

5 flows × 2 languages = 10 manual interactions. Documented as PR description checkboxes. Required before merge.

**Plus a 6th flow specifically for the estimation-path fix** (Option C), in both languages:
- Log an off-menu food with a natural unit: *"שתי פרוסות פיצה"* (he) / *"two slices of pizza"* (en).
- Expected preview: *"פיצה — 2 פרוסות (~200g)"* + reasonable macros (~540 cal). Pre-fix this would show `2g pizza` with ~6 cal.
- Confirm and verify the DB row writes the right gram amount (~200g, not 2g).

### Edge Cases (covered)

- `original_unit == "g"` → renders as `Xg` (task 11 render rule + task 12 grams test).
- `original_count == 1` → singular form (task 12 singular test).
- `original_count == 2.5` (non-integer) → plural form, rendered as `2.5` not `2.5.0` (the `:g` format).
- DB unit mismatch (e.g., user edits "1 cup" on a slice-only food) → tool returns error, surfaced via processing_results (task 14).
- Estimated unit mismatch when `default_unit_weight_g` is None → falls through to error path (task 15).
- Estimated unit mismatch when `default_unit_weight_g` is set but `default_unit != edit.new_unit` → error (task 15).
- Multi-edit batch where one edit fails and others succeed → only the failing item gets a FAILED result; others apply (the `continue` in task 15 + caller loop semantics).

### Edge Cases (NOT covered — deferred)

- LLM re-estimate fallback for non-default-unit edits on estimated items (defer per `## NOTES`).
- Hebrew gendered/dual plural forms (defer; singular vs plural is good enough).
- "Add item" edit type ("yes and also 2 slices of bread" — TASKS #12, defer).
- Cross-language input (user types `"תעשה 3 slices"` mixing he and en) — current parser will pick one or the other; not worth designing for.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

```bash
uv run ruff check src/ bot/ tests/
```

### Level 2: i18n boot check

```bash
uv run python -c "from src.i18n import MESSAGES; print(MESSAGES['confirmation_unit_label_slice_plural'])"
BOT_LANGUAGE=he uv run python -c "from src.i18n import MESSAGES; print(MESSAGES['confirmation_unit_label_slice_plural'])"
```

### Level 3: Schema check

```bash
uv run python -c "from src.schemas.confirmation_schema import ItemEdit; print(ItemEdit.model_fields['new_unit'].annotation)"
```

### Level 4: Targeted unit tests

```bash
uv run pytest tests/unit/test_confirmation_node.py -v
```

### Level 5: Full unit + integration suites

```bash
uv run pytest tests/unit/ -v
uv run pytest tests/integration/ -v
```

### Level 6: Dev-bot manual smoke

6 flows × 2 languages, documented as checkboxes in the PR. The 6th flow specifically validates the estimation-path fix (off-menu food logged with a natural unit).

---

## ACCEPTANCE CRITERIA

### State + estimation path (tasks 1-7)
- [ ] `MacroResult` carries `original_count: float` and `original_unit: str` populated by both DB and estimation paths in `calculate_macros_node`.
- [ ] **Estimation path passes `(count, unit)` to `_estimate_macros`**; the LLM emits `amount_g_estimated` and macros for that exact total. *"2 פרוסות פיצה"* lands as `amount_g≈200`, `original_count=2`, `original_unit="slice"` — not `amount_g=2, original_unit="g"` as today.
- [ ] `MacroEstimation` schema has required `amount_g_estimated: float` field.
- [ ] `prompts/macro_estimation.md` accepts `(count, unit, food_name)` and instructs the LLM to compute `amount_g_estimated = count × default_unit_weight_g` for natural-unit input.

### Render side (tasks 8-12)
- [ ] `_format_batch_preview` renders `{name} — {amount_g}g` for grams items (unchanged) and `{name} — {count} {label} ({amount_g}g)` for natural-unit items.
- [ ] Singular vs plural unit labels picked correctly (`count == 1` → singular).
- [ ] 32 new i18n keys (8 units × 2 forms × 2 langs); parity check green.
- [ ] Unit tests pass (existing + 3 new in test_confirmation_node + 3 new in test_calculate_macros_node).

### Edit side (tasks 13-19)
- [ ] `ItemEdit.new_amount_g` removed; `new_count` + `new_unit` added.
- [ ] DB-item edits pass `(new_count, new_unit)` to `calculate_food_macros` and propagate the result.
- [ ] Estimated-item edits: grams pass through; natural unit converts via `default_unit_weight_g`; mismatch surfaces FAILED ProcessingResult.
- [ ] `prompts/confirmation_parser.md` instructs the LLM to emit both `new_count` and `new_unit`, with the inheritance rule for count-only edits.
- [ ] `_parse_confirmation` batch_context includes `original_count` + `original_unit` per item.

### Validation gates (tasks 20-21)
- [ ] Full unit suite + integration suite pass; ruff clean.
- [ ] Manual smoke passes for all 6 flows × 2 languages, including the 6th flow that verifies estimated foods render with the user's natural unit.

---

## COMPLETION CHECKLIST

- [ ] All 21 tasks completed in order.
- [ ] Manual smoke passes for all 12 cases (6 flows × 2 langs).
- [ ] Commit + PR handled post-execution via `/commit` skill.
- [ ] Brain TASKS.md updated (manually, separate repo) with the deferred-eval follow-up.
- [ ] No edits outside the expected files: `state.py`, `estimation_schema.py`, `macro_estimation.md`, `calculate_macros_node.py`, `confirmation_node.py`, `confirmation_schema.py`, `confirmation_parser.md`, `i18n/__init__.py`, `i18n/en.yaml`, `i18n/he.yaml`, `test_confirmation_node.py`, `test_calculate_macros_node.py`.

---

## NOTES

### Why `original_unit: str` is required (not Optional)

Every `MacroResult` in the new world has `original_count` + `original_unit` populated by the writer (`calculate_macros_node`). Making them required (no `Optional`) avoids a class of "did we forget to set this?" bugs at the read sites. The TypedDict declaration is documentary; runtime safety comes from the writer always setting them. Direct access (`item["original_unit"]`) is the right pattern given bot restart-on-deploy makes orphaned in-flight checkpoints a non-issue today (see `## In-flight checkpoint compatibility` below).

### In-flight checkpoint compatibility

LangGraph state checkpoints can persist across deploys via the Postgres checkpointer. **However**, the bot's `user_sessions` dict is in-memory only (no Redis yet — TASKS Important #8). When the bot restarts:
1. `user_sessions` evaporates.
2. Next message from any user → bot has no `thread_id` → `_create_thread()` → fresh thread.
3. Any orphaned mid-flight thread sits in Postgres untouched, never reloaded.

So in production today, an in-flight HITL session built by old-shape code does NOT get resumed by new-shape code. We can use direct dict access without defensive `.get()`. **When TASKS #8 (Redis session persistence) lands**, this concern becomes real and we'll audit defensive reads as part of that work — alongside other shape changes likely to have accumulated by then.

### Why we replace `new_amount_g` instead of coexisting with `new_count`/`new_unit`

The only producer of `ItemEdit` is the LLM (controlled by the prompt). The only consumer is `_apply_edits`. There's no external API surface to be backward-compat for. Coexistence would cost two prompt rules ("when to emit which") + two code paths in `_apply_edits` to defend against… nothing. Replace is cleaner; removed the field.

### Why we don't LLM-re-estimate on unit mismatch (estimated items)

`default_unit_weight_g` covers the common case (most estimated items have it post-Plan-3). Falling back to a fresh LLM estimate on edge cases (e.g., user edits "2 slices pizza" → "1 cup") would:
- Add 1-3s latency to every edge-case edit.
- Introduce nondeterminism: the new estimate's macros may differ from the original's (LLM isn't perfectly self-consistent), confusing the user mid-conversation.
- Cost more tokens for a rare path.

Clean error message ("can only edit in grams or {default_unit}") is acceptable for POC. If we see real user complaints about the limitation, we revisit.

### Estimation-path natural-unit fix (Option C — included in this plan)

This plan **includes** the fix for the pre-existing bug where `calculate_macros_node` collapsed non-grams units to grams before estimation (so *"2 slices pizza"* got estimated for 2g). Tasks 2, 3, and 5 fold the fix in:

1. `MacroEstimation` schema gains a required `amount_g_estimated: float` field — the LLM explicitly states the gram amount it computed macros for. No inference; no `count × default_unit_weight_g` reconstruction.
2. `prompts/macro_estimation.md` is updated to accept `(count, unit, food_name)` and require the LLM to:
   - For grams input: `amount_g_estimated = count`.
   - For natural-unit input: estimate `default_unit_weight_g` for one of that unit, then `amount_g_estimated = count × default_unit_weight_g`. Macros are for that total.
3. `_estimate_macros` signature changes to `(food_name, count, unit, original_text)`. The HumanMessage to the LLM now passes "quantity: {count} {unit}". The returned `MacroResult.amount_g` comes from `result.amount_g_estimated`.

**Trust point**: the LLM is responsible for math consistency between `amount_g_estimated`, `default_unit_weight_g`, and the macros. Prompt instruction is explicit (`amount_g_estimated == count × default_unit_weight_g` for natural-unit input), but Pydantic accepts whatever value the LLM returns. If the LLM violates the constraint, the data is internally wrong but not crashy — caught only via dev-bot smoke or eval.

**Why we trust the LLM here**: it must already know "1 slice of pizza ≈ 100g" to populate `default_unit_weight_g` correctly today (this is the pre-existing Plan 3 estimation prompt's job). We're just asking it to also use that knowledge when computing the macros for the user's stated quantity, instead of the code blindly using `count` as grams. The cognitive task is the same.

**No estimation-prompt eval scaffold in this plan**. The TASKS already mentions an estimation eval as Plan 3 follow-up; bundling it here would compound scope. The dev-bot smoke flow #6 (off-menu pizza, 2 slices) catches the bug shape; subtle macro-accuracy regressions are out of scope until the estimation eval lands as its own piece of work.

**Future work** (not in this plan): widening the unit Literal beyond `g | piece | slice | scoop | bottle | cup | tbsp | tsp | can` (TASKS #9 escalation path) — when added, both `SingleFoodItem.unit`, `ItemEdit.new_unit`, and `MacroEstimation.default_unit` Literals must update together.

### Why the eval is its own commit (separate skill, separate plan)

The `eval-setup` skill has its own workflow for dataset design, evaluator selection, and notebook generation. It produces durable infrastructure (a dataset in LangSmith + a runnable notebook). Bundling it into a UX feature commit would couple unrelated lifecycles — the eval should outlive any single fix. Separate commit lets future readers find the eval scaffold easily and lets us re-use the same eval for other prompt changes (e.g., the unit-vocabulary-gap escalation in TASKS #9).
