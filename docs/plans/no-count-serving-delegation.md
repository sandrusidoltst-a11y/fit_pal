# Feature: No-count parser inputs delegate to catalog via `unit='serving'`

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files.

## Feature Description

When a user logs a food without specifying a quantity (e.g., `"מעדן חלבון"`, `"קפה"`, `"שייק חלבון"`), the input parser currently consults a hardcoded 4-bucket prompt rule that classifies the food (beverage → 240g, protein → 100g, fruit → 120g, anything else → "a reasonable per-serving weight") and emits `{count: <category default>, unit: "g"}`. Three problems with this:

1. **Eval/prompt mismatch.** Eval expects `מעדן חלבון = 130g` (real container weight); the prompt rule yields `100g` (generic protein default). Deterministic miss, not LLM noise.
2. **Multi-item instability.** Inside multi-item parses, the model sometimes drops the rule and emits `{count: 1, unit: "g"}` for the second item (logged: `1g of food`). Observed ~20% in dogfooding.
3. **Catalog ownership inversion.** Default serving weight per food belongs in the catalog (`food_items.unit_weights`) where the coach can curate it per food, not in a prompt that has no per-food context.

**The change:** parser stops guessing default grams. For no-quantity inputs it always emits `count=1, unit='serving', amount_g=<LLM estimate>`. The resolver chain (`resolve_amount_g`) checks `unit_weights["serving"]` for catalog-curated truth; if not registered, falls back to the parser's `amount_g`. Coach curates serving weights per food in the catalog as needed — loose mode, no migration required, incremental.

## User Story

As **the coach (and only user right now)**,
I want **the parser to defer to my catalog for default serving weights**,
So that **`"מעדן חלבון"` consistently logs at the right weight per my plan, and I can tune any food's no-count default by editing one JSONB field instead of editing the prompt**.

## Problem Statement

The default-serving rule in `prompts/input_parser.md` Step 2.4 hard-codes per-category gram defaults inside the prompt. This (a) creates a per-food precision ceiling the prompt can never reach (every food is generic), (b) destabilizes multi-item parses (model drops the rule under load), and (c) inverts ownership — coach-curated truth should live in the catalog, not the prompt.

## Solution Statement

Replace the per-category gram defaults with a single universal output: `count=1, unit='serving'`. Make `serving` a recognized (but optional) key in `food_items.unit_weights`. Let the resolver chain do its job — catalog hit when present, `amount_g` fallback when absent.

Three artifacts change:
1. `prompts/input_parser.md` — Step 2.4 rewrite, plus canonical-unit-vocabulary anchor in Step 2.2, plus tightened `amount_g`-required rule.
2. `notebooks/evals/eval_input_parser_hebrew.py` — flip 4 no-count expectations from `{count: <grams>, unit: "g"}` to `{count: 1, unit: "serving"}`. Add a parser-shape assertion: any item with `unit != "g"` must have non-null numeric `amount_g`.
3. `tests/unit/test_food_service_helpers.py` — add `serving`-specific tests for `resolve_amount_g` (already covers the chain mechanics for other units; new tests just exercise `unit='serving'` against the three resolver branches).

No schema migration. No catalog data backfill. No new files in `src/`. Coach adds `serving` to specific food rows when they want deterministic behavior for that food — incremental curation, pull-based.

## Feature Metadata

**Feature Type**: Refactor (prompt + eval + tests; no production code changes)
**Estimated Complexity**: Low
**Primary Systems Affected**: input parser prompt, Hebrew input-parser eval, food-service resolver unit tests
**Dependencies**: None new. Relies on existing `resolve_amount_g` chain (PR #30) and existing `food_items.unit_weights` JSONB column.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — YOU MUST READ THESE BEFORE IMPLEMENTING

- `prompts/input_parser.md` (entire file) — Why: file you're rewriting. Pay particular attention to Step 2.2 (lines ~61-75), Step 2.3 (lines ~77-91), Step 2.4 (lines ~96-108). Step 2.3 was just rewritten in commit `fc666f6` to remove the gram-native conversion — your work continues that direction.

- `src/services/food_service.py` (lines 31-71) — Why: `resolve_amount_g` resolver chain. The contract you're relying on. Five rules in order: grams passthrough → `unit_weights` direct hit → `unit_synonyms` redirect → `amount_g` safety net → last-resort fallback. Your new tests target rule 2 vs rule 4 behavior for `unit='serving'`.

- `src/agents/nodes/calculate_macros_node.py` (entire file, especially lines 128-185 `_estimate_macros`) — Why: estimation path. After the change, no-count inputs reaching this path will have `unit='serving', amount_g=<estimate>`. `_estimate_macros` uses `amount_g` directly when present; falls back to count-as-grams with a warning when missing. This is why the eval needs to assert `amount_g` is always non-null when `unit != 'g'` — otherwise estimation path silently degrades.

- `src/schemas/input_schema.py` (lines 16-42, `SingleFoodItem`) — Why: parser output schema. `unit` is free-form `str` (default `"g"`), `amount_g` is `Optional[float]`. No schema change needed; the field descriptions can be tightened in the same task as the prompt edit if you want, but optional.

- `src/models.py` (lines 14-30 `FoodItem`, lines 115-138 `CoachFoodMapping`) — Why: `food_items.unit_weights` is a `JSONB` column with `server_default="{}"`. `coach_food_mappings.serving_amount_g` exists on a different table (per-coach overlay) — separate concept, NOT the same as `unit_weights["serving"]`. Resolver only reads from `food_items.unit_weights` — coach overrides are not load-bearing here.

- `notebooks/evals/eval_input_parser_hebrew.py` — Why: file you're updating. Pay attention to:
  - `EXAMPLES` list (top of file, lines 40-430-ish) — find every no-count example and flip its expectation
  - `correct_serving` evaluator (lines 474-513) — currently only checks `count` + `unit`; you may extend it to assert `amount_g` presence
  - `run_input_parser` wrapper (lines 443-461) — already returns the parser output unchanged; should not need touching
  - `_resolve_date_sentinel` (lines 516-537) — pattern to follow if you want a sentinel for `amount_g != null` style assertions

- `tests/unit/test_food_service_helpers.py` (entire file, especially `TestResolveAmountG` class lines 30-65) — Why: existing test pattern for `resolve_amount_g`. Uses `MagicMock` to fake `FoodItem` with arbitrary `unit_weights` / `unit_synonyms`. Your new `serving`-specific tests mirror this exactly.

- `commit_logs/2026-05-16_17-27-11_keep-natural-units-drop-parser-side-gram-conversion.md` — Why: directly prior commit on the same branch. Sets context for the resolver chain's load-bearing role and the "stale assumption" pattern you're fixing again.

### New Files to Create

None. This is a pure refactor across three existing files (plus one new commit log + plan markdown).

### Relevant Documentation — YOU SHOULD READ THESE BEFORE IMPLEMENTING

- LangSmith eval evaluator function signatures: https://docs.smith.langchain.com/evaluation/how_to_guides/custom_evaluator
  - Why: if you extend `correct_serving` to check `amount_g`, the evaluator must still return `{"key": ..., "score": ..., "comment": ...}`.

- LangChain structured-output: https://python.langchain.com/docs/concepts/structured_outputs
  - Why: `input_parser_node` uses `.with_structured_output(UserIntent)`. The schema's field descriptions (Pydantic `Field(description=...)`) become part of the prompt the LLM sees. Tightening field descriptions in `src/schemas/input_schema.py` is an *additive* lever beyond the prompt edit — use sparingly to avoid duplication.

### Patterns to Follow

**Prompt-edit style (current `input_parser.md`):**
- Numbered top-level steps (`### Step 1`, `### Step 2`), then bold sub-rules (`**Rule name**:`), then bullets, then `Examples:` with backtick code blocks.
- Worked examples use real Hebrew + concrete dates. Today's date stays static in the file (e.g., `today = 2026-05-16`) — accepted maintenance debt, refreshed when the prompt changes.
- Critical rules get an explicit `**Critical**:` callout at the end of the step.

**Eval expectation shape (current `EXAMPLES` list):**
- Each example is a dict with `question`, `action`, `items`, `item_count`, `consumed_at`, `start_date`, `end_date` (and sometimes `category`).
- Each item in `items` has `food_name`, `count`, `unit` — and optionally additional asserted fields. The `correct_serving` evaluator pairs items by index, so item order matters.

**Unit-test style for resolver (`TestResolveAmountG`):**
- `_food(**weights_overrides)` helper builds a `MagicMock` with `unit_weights` / `unit_synonyms` / `name_en`. No real `FoodItem` instantiation. No DB.
- Test class groups related cases. Each test is a single behavioral assertion.
- Warning cases use `caplog` fixture: `with caplog.at_level(logging.WARNING):`.

**Commit-and-log pattern (per `.claude/skills/commit/SKILL.md`):**
- Commit log goes in `commit_logs/YYYY-MM-DD_HH-MM-SS_brief-description.md` BEFORE staging.
- Commit log + code + plan markdown are staged together and committed as one unit.
- No follow-up `docs:` commit just for the log.

---

## IMPLEMENTATION PLAN

### Phase 1: Prompt rewrite

Replace Step 2.4 of `prompts/input_parser.md` with the new no-count rule. Add the canonical-unit-vocabulary anchor to Step 2.2. Tighten the `amount_g` rule's prominence.

**Tasks:**

- Rewrite Step 2.4 default-serving rule: no-count → always `count=1, unit='serving', amount_g=<LLM estimate>`.
- Drop the 4 hardcoded category bullets (beverages 240g, protein 100g, fruit 120g, anything else).
- Drop the "never return `count=0` or `count=1` with `unit='g'`" guard (no longer needed; the no-count case is now `unit='serving'`).
- Drop the "Why grams as default" rationale paragraph (stale assumption — pre-PR-#30).
- Update the three worked examples in Step 2.4 to use `serving`.
- Add a canonical-unit-vocabulary anchor near the top of Step 2.2 listing the catalog's known canonical unit keys, positive-framed: "use one of these when an obvious match exists for the user's unit; otherwise emit the user's word verbatim."
- Tighten the `amount_g`-required-when-`unit != "g"` rule: same wording but elevated (e.g., bullet promoted to its own line with `**REQUIRED**:`), since it's now load-bearing for the no-count case too.

### Phase 2: Eval expectation flips + amount_g assertion

Update `notebooks/evals/eval_input_parser_hebrew.py` to match the new parser output shape. Add a new evaluator dimension that catches `amount_g` drop on non-gram units.

**Tasks:**

- Flip every no-count example expectation from `{count: <grams>, unit: "g"}` to `{count: 1, unit: "serving"}`. Confirmed candidates from the current file: `"קפה"`, `"מעדן חלבון"`, the `"פסטה עם גבינה לצהריים"` items (both pasta and cheese), the `"שייק חלבון"` item inside `"שתיתי שייק חלבון אחרי אימון"`, and the `"מעדן חלבון"` item inside `"שתי פרוסות גבינה עם מעדן חלבון"`. Audit the full `EXAMPLES` list for any others.
- Do NOT flip the count-given examples (`"200 גרם עוף"`, `"חצי בננה"`, `"חצי כוס אורז"`, `"שלוש ביצים"`, etc.) — those keep their current shape.
- Add a new evaluator function `amount_g_present_when_non_gram(outputs, reference_outputs) -> dict` that fails if any item has `unit != "g"` AND `amount_g` is `None`. Returns `{"key": "amount_g_present_when_non_gram", "score": <fraction>, "comment": <which items failed>}`. Per-item granularity, score = fraction passing.
- Register the new evaluator in the `evaluators=[...]` list at the bottom of the file (around line 766).
- Add 1-2 new examples covering no-count inputs for foods we know are NOT in the catalog. The point is just to verify the parser shape — eval already runs the parser in isolation, no resolver involvement. Pick foods that are obviously novel, e.g., `"שתיתי קולה דיאט"` ("I drank diet coke") — assuming diet coke isn't catalogued.

### Phase 3: Unit tests for `resolve_amount_g` with `unit='serving'`

Add three test cases to `tests/unit/test_food_service_helpers.py::TestResolveAmountG` covering the three branches the resolver takes when `unit='serving'`.

**Tasks:**

- Test: `serving` registered in `unit_weights` → catalog wins, ignores `llm_estimated_amount_g` even if present.
- Test: `serving` NOT in `unit_weights`, `llm_estimated_amount_g` present → falls back to amount_g.
- Test: `serving` not in `unit_weights`, no `llm_estimated_amount_g` → last-resort fallback (returns `count`, logs warning). Use `caplog` like existing `test_last_resort_returns_count_when_no_estimate`.

### Phase 4: Subset eval + full eval validation

Use `eval_subset.py` (from prior commit on this branch) to verify the no-count cases pass before running the full 35-example eval. Catch regressions on Bucket A (which we just fixed) and Bucket B (the new design).

**Tasks:**

- Run `uv run python notebooks/evals/eval_subset.py "מעדן חלבון" "קפה" "פסטה עם גבינה" "שייק חלבון"` after the prompt + eval changes. Verify all return `unit='serving', count=1, amount_g=<number>`.
- Run the full `uv run python notebooks/evals/eval_input_parser_hebrew.py` to confirm 35-example aggregate. Target: `correct_action`, `correct_dates`, `correct_item_count`, `food_name_quality`, `no_consumed_at_on_query`, `no_query_dates_on_log_food`, `amount_g_present_when_non_gram` all at 100%. `correct_serving` should improve over the current 87% baseline (exact target depends on how many examples actually had the gram-default bug vs. other issues; record the new baseline regardless).
- Run unit tests: `uv run pytest tests/unit/test_food_service_helpers.py -v`. Three new tests pass.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### UPDATE `prompts/input_parser.md` Step 2.4 (default-serving rule)

- **IMPLEMENT**: Replace the entire current Step 2.4 block with a single rule: "When the user gives no quantity for a food item, ALWAYS emit `{count: 1, unit: 'serving', amount_g: <your best gram estimate for a typical serving of this food>}`. The downstream resolver will use the food catalog's registered serving weight if available, otherwise fall back to your `amount_g`."
- **PATTERN**: Match the prose style of the surrounding Step 2.2 and Step 2.3 — bold rule, bullet, examples block.
- **EXAMPLES** (include in the prompt verbatim, updated to the new shape):
  - `"I had chicken"` → `{food_name: "chicken", count: 1, unit: "serving", amount_g: 150}`
  - `"מעדן חלבון"` → `{food_name: "מעדן חלבון", count: 1, unit: "serving", amount_g: 130}`
  - `"drank coffee"` → `{food_name: "coffee", count: 1, unit: "serving", amount_g: 240}`
- **REMOVE**: the 4 category bullets, the "Why grams as default" paragraph, the "Never return `count=0` or `count=1` with `unit='g'`" guard.
- **GOTCHA**: do NOT add a "never use `piece` for no-count" or "never use `container`" line — negative directives confuse the model. Positive directive only: "always `unit='serving'`."
- **VALIDATE**: `grep -n "count=240, unit=\"g\"\|count=100, unit=\"g\"\|count=120, unit=\"g\"\|Never return" prompts/input_parser.md` — should return nothing.

### UPDATE `prompts/input_parser.md` Step 2.2 (add canonical vocabulary anchor)

- **IMPLEMENT**: Add one bullet near the top of Step 2.2, just after the existing `unit` is FREE-FORM line: "When the user used an explicit unit, prefer one of the catalog's canonical unit keys when an obvious equivalent exists: `g`, `piece`, `slice`, `cup`, `tbsp`, `tsp`, `bowl`, `scoop`, `container`, `bottle`, `can`, `serving`. If the user's word doesn't match any of these, emit it verbatim — the catalog's `unit_synonyms` may still resolve it."
- **GOTCHA**: list is hardcoded for v1. Future task could regenerate from `SELECT DISTINCT jsonb_object_keys(unit_weights) FROM food_items` at server startup, but that's out of scope here.
- **VALIDATE**: `grep -A 2 "canonical unit keys" prompts/input_parser.md` — verify presence.

### UPDATE `prompts/input_parser.md` Step 2.2 (elevate `amount_g`-required rule)

- **IMPLEMENT**: Promote the existing `amount_g` rule from a sub-bullet to a top-level `**REQUIRED**:` line within Step 2.2. Reword to emphasize the no-count case: "Whenever `unit != 'g'` (including `unit='serving'`), emit `amount_g` as your best gram estimate for the stated quantity. Never null. The resolver uses this as a safety net when the catalog doesn't have your unit registered for the food, AND it's the primary source of truth for foods not yet in the catalog (estimation path)."
- **PATTERN**: Match the `**Critical**` callout style used at the end of Step 1's QUERY_DAILY_STATS section.
- **VALIDATE**: `grep -B 1 -A 3 "REQUIRED" prompts/input_parser.md` — verify presence and prominence.

### UPDATE `notebooks/evals/eval_input_parser_hebrew.py` — flip no-count expectations

- **IMPLEMENT**: For every example in `EXAMPLES` where the parser previously emitted a hardcoded gram default for an item with no user-stated quantity, change the item's expectation to `{"food_name": <same>, "count": 1, "unit": "serving"}`.
- **CONFIRMED CANDIDATES** (audit the full file for any missed ones):
  - `"קפה"` (alone) — flip
  - `"מעדן חלבון"` (alone) — flip
  - `"פסטה עם גבינה לצהריים"` — both items flip (pasta and cheese)
  - `"שתיתי שייק חלבון אחרי אימון"` — `שייק חלבון` item flips
  - `"שתי פרוסות גבינה עם מעדן חלבון"` — `מעדן חלבון` item flips; cheese stays `{2, slice}` (user specified `שתי פרוסות`)
- **PATTERN**: each example dict shape stays the same; only the `items[i].count` and `items[i].unit` change.
- **DO NOT FLIP**: any example where the user specified a count or unit (`"200 גרם עוף"`, `"חצי בננה"`, `"שלוש ביצים"`, `"חצי כוס אורז"`, etc.). Those keep current shape.
- **VALIDATE**: `uv run python -c "from notebooks.evals.eval_input_parser_hebrew import EXAMPLES; print(sum(1 for ex in EXAMPLES for it in ex.get('items', []) if it.get('unit') == 'serving'))"` — should print at least 5.

### ADD `amount_g_present_when_non_gram` evaluator to `notebooks/evals/eval_input_parser_hebrew.py`

- **IMPLEMENT**: Add a new sync evaluator function near the other evaluators (after `no_query_dates_on_log_food`, around line 580):
  ```python
  def amount_g_present_when_non_gram(outputs: dict, reference_outputs: dict) -> dict:
      """Fail if any item with unit != 'g' is missing a numeric amount_g.

      With the no-count → unit='serving' design, amount_g is load-bearing
      for both the resolver fallback (when catalog doesn't have the unit)
      and the estimation path (when the food isn't in the catalog at all).
      A null amount_g on a non-gram unit silently degrades downstream gram math.
      """
      items = outputs.get("items", [])
      non_gram_items = [it for it in items if it.get("unit") != "g"]
      if not non_gram_items:
          return {"key": "amount_g_present_when_non_gram", "score": 1.0, "comment": "No non-gram items"}
      bad = [it for it in non_gram_items if not isinstance(it.get("amount_g"), (int, float))]
      score = (len(non_gram_items) - len(bad)) / len(non_gram_items)
      comment = (
          "; ".join(f"{it.get('food_name','?')}: unit={it.get('unit')} amount_g={it.get('amount_g')}" for it in bad)
          or "all non-gram items have amount_g"
      )
      return {"key": "amount_g_present_when_non_gram", "score": score, "comment": comment}
  ```
- **REGISTER**: add `amount_g_present_when_non_gram` to the `evaluators=[...]` kwarg passed to `client.evaluate(...)` at the bottom of the file (around line 766).
- **GOTCHA**: don't pair this with `reference_outputs` — the check is purely about the parser's output shape; the expected items in `EXAMPLES` don't need to assert `amount_g`. Keep the existing `correct_serving` evaluator unchanged.
- **VALIDATE**: `grep -n "amount_g_present_when_non_gram" notebooks/evals/eval_input_parser_hebrew.py` — should match the def line and the registration line.

### ADD a no-count estimation-path example to `notebooks/evals/eval_input_parser_hebrew.py`

- **IMPLEMENT**: Add 1-2 examples in `EXAMPLES` for foods that are NOT in the catalog (estimation-path candidates). Example shape:
  ```python
  {
      "question": "שתיתי קולה דיאט",
      "action": "LOG_FOOD",
      "items": [{"food_name": "קולה דיאט", "count": 1, "unit": "serving"}],
      "item_count": 1,
      "consumed_at": None,
      "start_date": None,
      "end_date": None,
      "category": "estimation_path_no_count",
  },
  ```
- **GOTCHA**: pick a food you genuinely believe is NOT in the seeded catalog. The eval only checks parser output, so catalog membership doesn't affect the assertion — but the example serves as documentation of the intended estimation-path behavior.
- **VALIDATE**: `uv run python notebooks/evals/eval_subset.py "קולה דיאט"` — should pass `unit='serving', count=1, amount_g=<num>`.

### ADD three `serving`-specific tests to `tests/unit/test_food_service_helpers.py::TestResolveAmountG`

- **IMPLEMENT**: append three test methods to `TestResolveAmountG`:
  ```python
  def test_serving_registered_in_unit_weights_wins(self):
      food = _food(unit_weights={"serving": 130.0}, name_en="Protein Pudding")
      # Catalog wins even when amount_g is present
      assert resolve_amount_g(food, "serving", 1.0, llm_estimated_amount_g=100.0) == 130.0

  def test_serving_not_registered_falls_back_to_amount_g(self):
      food = _food(unit_weights={"piece": 50.0}, name_en="New Food")
      assert resolve_amount_g(food, "serving", 1.0, llm_estimated_amount_g=150.0) == 150.0

  def test_serving_not_registered_no_amount_g_uses_last_resort(self, caplog):
      food = _food(unit_weights={}, name_en="New Food")
      with caplog.at_level(logging.WARNING):
          assert resolve_amount_g(food, "serving", 1.0) == 1.0
  ```
- **PATTERN**: mirror `test_unit_weights_direct_hit`, `test_falls_back_to_llm_estimate`, `test_last_resort_returns_count_when_no_estimate` exactly.
- **IMPORTS**: `_food`, `resolve_amount_g`, `logging` (caplog), `MagicMock` are already imported in the file.
- **VALIDATE**: `uv run pytest tests/unit/test_food_service_helpers.py::TestResolveAmountG -v` — three new tests pass, existing tests still pass.

### RUN subset eval to confirm no-count behavior

- **IMPLEMENT**: `uv run python notebooks/evals/eval_subset.py "מעדן חלבון" "קפה" "פסטה עם גבינה" "שייק חלבון" "קולה דיאט"`
- **EXPECT**: every output line shows `unit='serving', count=1.0, amount_g=<number>`. `correct_serving` and `amount_g_present_when_non_gram` both pass for these inputs.
- **GOTCHA**: subset script has a substring-match dedupe; should work cleanly here.

### RUN full Hebrew eval to confirm aggregate

- **IMPLEMENT**: `uv run python notebooks/evals/eval_input_parser_hebrew.py 2>&1 | tail -20`
- **EXPECT**: all dimensions at 100% except `correct_serving`, which should be measurably higher than the pre-change 87% baseline. Record the new baseline in the commit log. `amount_g_present_when_non_gram` at 100% (any drop indicates the parser is dropping `amount_g` somewhere — investigate before committing).
- **GOTCHA**: serving still won't hit 100% — `"פסטה עם גבינה לצהריים"`'s eval expectation (200g pasta + 30g cheese — Bucket C, aspirational meal-context defaults) is still in place. This task does not relax that expectation. If you want to fix it, that's a follow-up.

### RUN unit + integration test suites for regression

- **IMPLEMENT**: `uv run pytest tests/unit/ -v` then `uv run pytest tests/integration/ -v`
- **EXPECT**: zero regressions. Unit suite gains 3 tests. Integration suite unchanged.

### DRAFT commit log and PR reading guide

- **IMPLEMENT**: create `commit_logs/YYYY-MM-DD_HH-MM-SS_no-count-serving-delegation.md` documenting: why (Bucket B problem + ownership inversion), what changed (prompt + eval + tests), validation (before/after eval scores, unit test additions), what's next (coach incrementally registers `serving` weights as needed; estimated-food rows still need auto-registration consideration as a future task).
- **OPTIONAL** (decide based on diff size): If the diff touches 4+ files or you want to make the reviewer's life easier, draft a reading guide at `docs/plans/no-count-serving-delegation-review-guide.md` walking the reviewer through: prompt edits first (the keystone), then eval flips (the test surface that justifies the edit), then unit tests (the deterministic part), then estimation-path notes (why we explicitly chose Option A — no auto-registration).
- **PATTERN**: follow `.claude/skills/commit/SKILL.md` section 3 for reading-guide structure if drafting one.

### COMMIT all changes as one atomic commit

- **IMPLEMENT**: `git add prompts/input_parser.md notebooks/evals/eval_input_parser_hebrew.py tests/unit/test_food_service_helpers.py commit_logs/<file>.md docs/plans/no-count-serving-delegation.md` then `git commit` with a `refactor(parser):` or `fix(parser):` prefix matching the project's tag convention.
- **GOTCHA**: do NOT commit `eval_subset.py` changes if you didn't make any (it was already committed in `fc666f6`).
- **VALIDATE**: `git log -1 --stat` — verify commit landed with expected files.

---

## TESTING STRATEGY

### Unit Tests

Three new tests in `tests/unit/test_food_service_helpers.py::TestResolveAmountG` covering the three resolver branches for `unit='serving'`. Follows existing pattern: `MagicMock` `FoodItem`, no DB, sub-second. No new test files. No fixtures hoisted.

### Integration Tests

None added. The parser → resolver chain has no shared state to test end-to-end at the DB level beyond what existing tests cover. If you change your mind during execution and want one, a candidate would be a `tests/integration/` test that seeds a `food_items` row with `unit_weights={"serving": 130}` and asserts `calculate_food_macros(food_id, count=1, unit="serving")` returns gram-total 130 — but this duplicates `resolve_amount_g` unit-test coverage with extra DB cost.

### Edge Cases

- **Parser drops `amount_g` for `unit='serving'`**: caught by new `amount_g_present_when_non_gram` evaluator. Estimation path falls back to count-as-grams with warning; logged value would be `1g` — clearly broken, will fail eval.
- **Model emits `unit='Serving'` or `unit='SERVING'`**: not handled. Resolver does case-sensitive string match. Worth flagging if observed, not fixing pre-emptively.
- **Model emits `unit='piece'` or `unit='container'` for no-count case**: prompt drift. Resolver falls through to `amount_g` if the food doesn't have `piece`/`container` registered, which is degraded but not broken. Eval catches this only if expectation is `serving` — which it is after the flip.
- **`amount_g` is `0` or negative**: type check (`isinstance(..., (int, float))`) passes for `0`, but downstream macro math would produce zero macros. Worth a sanity check in the evaluator if seen.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

```bash
uv run ruff check .
```

### Level 2: Unit Tests

```bash
uv run pytest tests/unit/ -v
uv run pytest tests/unit/test_food_service_helpers.py::TestResolveAmountG -v  # narrow
```

### Level 3: Integration Tests

```bash
uv run pytest tests/integration/ -v
```

### Level 4: Eval — Subset (fast feedback during development)

```bash
uv run python notebooks/evals/eval_subset.py "מעדן חלבון" "קפה" "פסטה עם גבינה" "שייק חלבון"
```

### Level 5: Eval — Full (final gate before commit)

```bash
uv run python notebooks/evals/eval_input_parser_hebrew.py
```

Expected: 6 of 7 dimensions at 100% (excluding `correct_serving`, which still has Bucket C aspirational expectations in place). `amount_g_present_when_non_gram` at 100%.

### Level 6: Manual sanity check (optional)

Spot-check the prompt rewrite is well-formed by skimming `prompts/input_parser.md` Steps 2.2-2.4. Look for: positive-only directives in 2.4, canonical vocab list in 2.2, `**REQUIRED**` callout on the `amount_g` rule.

---

## ACCEPTANCE CRITERIA

- [ ] `prompts/input_parser.md` Step 2.4 rewritten: no-count → `count=1, unit='serving', amount_g=<estimate>`. No hardcoded gram categories. No `count=1, unit='g'` guard. No "grams as default" rationale paragraph.
- [ ] `prompts/input_parser.md` Step 2.2 includes the canonical unit vocabulary anchor and elevates the `amount_g`-required rule.
- [ ] All no-count examples in `notebooks/evals/eval_input_parser_hebrew.py::EXAMPLES` updated to `{count: 1, unit: 'serving'}`.
- [ ] `amount_g_present_when_non_gram` evaluator function exists and is registered in the evaluators list.
- [ ] At least one no-count example for a food NOT in the catalog (estimation-path documentation).
- [ ] Three new tests in `TestResolveAmountG` covering `serving` registered, `serving` not registered + amount_g, last-resort.
- [ ] Full eval passes with `amount_g_present_when_non_gram` at 100%, and `correct_serving` measurably higher than 87% baseline.
- [ ] `uv run ruff check .` passes.
- [ ] `uv run pytest tests/unit/ tests/integration/` passes (no regressions).
- [ ] Commit log written and committed atomically with all changes.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order.
- [ ] Each task validation passed immediately.
- [ ] All validation commands executed successfully.
- [ ] Subset eval shows `unit='serving', count=1, amount_g=<num>` for every no-count target.
- [ ] Full eval aggregate recorded in commit log.
- [ ] Unit test suite passes (3 new + all existing).
- [ ] Integration test suite unchanged.
- [ ] No linting errors.
- [ ] Commit log + plan + diff committed as single unit.
- [ ] Branch is `fix/last-N-days-rolling-exclusive` (already in progress) OR a new branch named like `refactor/no-count-serving-delegation` — decide based on whether to ship this with the prior two commits or as a separate PR.

---

## NOTES

**Design decisions and tradeoffs:**

- **Option A (loose mode) chosen over Option B (auto-register `serving` on estimated-food commit).** Rationale: cleaner separation (catalog truth vs LLM estimate), no production users currently affected, easier to revisit once the coach-dashboard exists for review workflows. The cost: foods not yet curated with `serving` will have run-to-run LLM variance on amount_g for no-count inputs. Accepted because incremental curation pull is more honest than auto-locking-in a single LLM guess.

- **`coach_food_mappings.serving_amount_g` is NOT touched.** It's a per-coach overlay on a different table, used for plan-compliance math (`compute_servings`), not for what gets logged. Resolver chain stays base-catalog-only. If you ever want coach override at the resolver level, that's a separate ADR — it changes the meaning of "logged grams" depending on which coach the user has, which has real implications for shared food data.

- **Canonical unit vocabulary is hardcoded in the prompt for v1.** Future enhancement: regenerate from `SELECT DISTINCT jsonb_object_keys(unit_weights) FROM food_items` at server startup, inject into the prompt. Out of scope here.

- **`correct_serving` evaluator NOT extended to check `amount_g` values** (only presence via the new evaluator). Reason: `amount_g` is an LLM estimate with inherent variance; asserting exact values would re-introduce the same kind of eval flake we just eliminated by deleting the hardcoded gram defaults. The deterministic check is "presence when required"; the value correctness is the resolver's problem and is unit-tested directly.

- **Bucket C ("פסטה עם גבינה לצהריים" expecting 200g pasta + 30g cheese) is intentionally left in place.** That eval expectation asks the parser for meal-context awareness it doesn't and shouldn't have. After this change, the parser will return `count=1, unit='serving'` for both items — which the eval will still mark as wrong (count mismatch: 1 vs 200/30). That's expected. The follow-up is to relax the eval expectation, not the parser.

- **Today's date in the prompt's worked examples stays `2026-05-16`** (from the prior commit on this branch). Not refreshed every change — too much churn for too little value. Acceptable maintenance debt.

**Estimated confidence in one-pass execution:** 9/10. The changes are narrow, the patterns are well-established in the codebase, the validation chain is layered (subset eval → full eval → unit tests), and the rollback path is one `git revert`. The one risk: an LLM behavior surprise where the model resists emitting `unit='serving'` for the no-count case despite the explicit directive — in which case prompt iteration is needed. Subset eval catches this in under 30 seconds.
