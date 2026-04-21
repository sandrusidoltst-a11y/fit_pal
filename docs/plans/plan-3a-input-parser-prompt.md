# Plan 3a — Input Parser Prompt Rewrite

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Rewrite `prompts/input_parser.md` to align with the two-table food catalog schema landed in Plan 1 + the code refactor in Plan 2. The parser today emits an `amount_g` (mandatory grams normalization). After Plan 2, the schema expects `{count, unit}` where `unit ∈ {g, piece, slice, scoop, bottle, cup, tbsp, tsp, can}`. Until this prompt rewrite ships, the bot is end-to-end broken on any non-gram input.

This is **Plan 3a of 5** in the food catalog prompt-rewrite trilogy (which is itself "Plan 3" of the broader food catalog trilogy):

| Sub-plan | Scope | Status |
|---|---|---|
| **Plan 3a (this doc)** | `prompts/input_parser.md` rewrite + static unit-bucket table | Ready to execute |
| Plan 3b | `prompts/macro_estimation.md` rewrite | Pending |
| Plan 3c | `prompts/agent_selection.md` rewrite | Pending |
| Plan 3d | `prompts/response_generator.md` rewrite | Pending |
| Plan 3e | `prompts/confirmation_parser.md` rewrite + `ItemEdit` schema extension | Pending |

## User Story

As **Dolev** (coach + only trainee during POC),
I want the input parser to emit `{count, unit}` natively for non-gram foods (eggs as pieces, bread as slices, beer as bottles), and grams for everything else,
So that the bot resolves macros against the food's true natural unit instead of failing or computing 100g of egg.

## Problem Statement

Plan 2 shipped:
- `SingleFoodItem.count: float` + `SingleFoodItem.unit: Literal[g | piece | slice | scoop | bottle | cup | tbsp | tsp | can]` (default `"g"`)
- `resolve_amount_g(food, unit, count)` in `src/services/food_service.py:31` — strict resolver: `unit="g"` always passes; any other unit must match `food.default_unit` exactly, or `ValueError`

But `prompts/input_parser.md` still says:
> *"MANDATORY: Convert all quantities (cups, slices, pieces, etc.) into an estimated weight in grams."*

This means:
- "2 eggs" → parser emits `{count: 100, unit: "g"}` instead of `{count: 2, unit: "piece"}` → macros computed against 100g of egg (wrong by ~2x; an egg is ~50g)
- "1 pita" → `{count: 90, unit: "g"}` instead of `{count: 1, unit: "piece"}` → loses serving signal (1 pita = 1 carb serving for the coach's method)
- "שלוש ביצים" (Hebrew word-form quantifier work from commit `a56f23d`) still emits 150g instead of `{count: 3, unit: "piece"}`

The contract mismatch is silent — schemas validate fine because `unit` defaults to `"g"`, but every non-gram food is parsed wrong.

## Solution Statement

Rewrite the prompt to:
1. **Drop the mandatory grams normalization.** Parser emits `{count, unit}` matching the true natural unit of the food when it can (using a static reference table of catalog foods that have non-gram natural units).
2. **Embed a static unit-bucket table** directly in the prompt — inverted shape (`unit → list of foods`), only listing the 28 non-gram foods from `data/canonical_food_catalog.csv`. Foods not listed default to grams.
3. **Default to grams when the user gives no quantity.** Safer than guessing a non-gram unit (mismatched non-gram units fail the resolver; grams always pass).
4. **Drop the "translate to English" implication** in the search-friendly naming section. Bilingual search now works on `name_en` OR `name_he`, so the parser stays language-neutral and emits clean canonical names without forced translation.
5. **Preserve the Hebrew quantifier work** from commit `a56f23d` (word-form numerals, multi-item scoping) — these were big accuracy wins (61%→79%) and only their *output target* changes (grams → count/unit).

## Feature Metadata

**Feature Type**: Prompt rewrite (no code changes, no schema changes)
**Estimated Complexity**: Low — single file edit, no migrations, no new dependencies
**Primary Systems Affected**: `prompts/input_parser.md` (only)
**Dependencies**: Plan 2 shipped (commit `e27e8e9`) — `SingleFoodItem` schema with `count`/`unit` fields; `resolve_amount_g` in `food_service.py`

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: YOU MUST READ THESE BEFORE IMPLEMENTING

**The prompt being rewritten:**
- `prompts/input_parser.md` (entire file, ~80 lines) — current prompt with mandatory grams normalization

**Schema contract the prompt must satisfy:**
- `src/schemas/input_schema.py` (lines 16-30) — `SingleFoodItem`: `food_name: str`, `count: float`, `unit: Literal[...]`, `original_text: str`. The `unit` Literal set is the only set of values the LLM may emit.
- `src/agents/state.py` (lines 8-19) — `PendingFoodItem` TypedDict mirrors `SingleFoodItem.model_dump()`.

**Resolver the parser's output is consumed by:**
- `src/services/food_service.py` (lines 31-47) — `resolve_amount_g(food, unit, count)`. Two safe paths: `unit == "g"` (always passes), or `unit == food.default_unit` (passes when matches). Any other case raises `ValueError`.
- `src/services/food_service.py` (lines 285-311) — `calculate_food_macros` tool. Returns `{"error": "..."}` when resolver fails — that error then surfaces through `processing_results` as `FAILED`.

**Source of truth for the unit-bucket table:**
- `data/canonical_food_catalog.csv` (93 rows) — column `default_unit` defines the true natural unit per food. Rows with `default_unit != 'g'` are the only ones that need to appear in the prompt's reference table (28 of 93).

**Node that loads and uses the prompt:**
- `src/agents/nodes/input_node.py` (lines 14-20) — prompt is loaded once at module import via `open(...)`. No runtime injection beyond the system time prefix at line 46. Static prompt edit takes effect on next import (= next process restart / dev server reload).

**Existing eval against the prompt:**
- `notebooks/evals/eval_input_parser_hebrew.py` — Hebrew dataset, current `amount_accuracy` baseline 79% (post commit `a56f23d`). After this rewrite, dataset itself needs an update (target field shape changed) — that's a Plan 3a follow-up (see Validation section).

### New Files to Create

None. This plan modifies a single existing file.

### Relevant Documentation

- Pointers doc: `brain/planning/food-catalog-plan-3-pointers.md` (vault path) — design rationale for the prompt-rewrite trilogy
- Architectural follow-ups deferred from this plan: `brain/planning/parser-architectural-followups.md`
- Plan 1 schema foundation: `commit_logs/2026-04-18_22-33-24_feat-food-catalog-migration-plan-1.md`
- Plan 2 code refactor: `commit_logs/2026-04-19_00-08-28_feat-food-catalog-plan-2-code-refactor.md`

### Patterns to Follow

**Prompt structure** — keep the existing two-step shape (Step 1: Identify Intent, Step 2: Execute Strategy). Reviewers grep this file by section header; preserve them unless replaced.

**Numbered sub-rules under "IF action is LOG_FOOD"** — current prompt has 6 numbered sub-rules. Keep the numbered shape. Renumber as needed.

**Hebrew examples** — current prompt uses `"שלוש ביצים" → 150g` style examples. Mirror that exact style for the new examples (`"שלוש ביצים" → {count: 3, unit: "piece"}`).

**No commentary outside prompt content** — the file is loaded literally as the system message. No "# Notes for Claude" or similar at the top — the LLM sees everything.

---

## LOCKED DESIGN DECISIONS

These were decided during the 2026-04-20 design call. Each is intentionally chosen — re-litigate only with explicit reason.

### 1. Parser cannot know `default_unit` at parse time → use a static table + grams fallback

**Decision.** The parser has no DB access, so it cannot look up a given food's `default_unit` dynamically. Instead, embed a static reference table of the 28 catalog foods that have non-gram `default_unit`, and instruct the LLM to default to grams for anything not in the table.

**Why not.** The pointers doc originally framed this as *"if unit doesn't match the food's `default_unit`, fall back to grams"* — but the parser literally cannot check that condition. The static table is the parse-time approximation of that rule.

**Architectural follow-ups deferred:** parser retry loop on `UNIT_MISMATCH`, ContextSchema injection of unit hints (multi-coach), full plan injection. All captured in `brain/planning/parser-architectural-followups.md`.

### 2. Default to grams when no quantity is given (Option A)

**Decision.** When the user mentions a food without a quantity ("I had chicken", "ate eggs"), the parser emits `{count: <default_grams>, unit: "g"}` using per-category gram defaults (protein 100g, beverage 240g, fruit 120g) — *regardless* of whether the food has a non-gram natural unit.

**Why.** When the user isn't explicit, the safest emission is grams. Non-gram guesses can fail the resolver (`unit` mismatch → `ValueError` → `FAILED`). Grams always resolve. Even if "I had an egg" emits `{100, g}` — silly but safe — the resolver accepts it and the user sees a normal HITL preview they can correct.

**Why not Option B (natural unit when obvious).** Tempting because it captures user intent better, but "obvious" is parser-judgement and we don't have the data to trust the LLM on this yet. Revisit post-eval.

### 3. Hebrew quantifier table + multi-item scoping survive — only the output target changes

**Decision.** Keep the Hebrew word-form numerals table (שתי/שלוש/חצי/רבע/...) and the multi-item scoping rule from commit `a56f23d` exactly as-is. Only the example outputs change format: grams → count/unit.

**Why.** Commit `a56f23d` lifted `amount_accuracy` from 61% to 79% on Hebrew dataset. That work is independent of the count/unit migration — it's about correctly *parsing* the quantity, not about *which unit* to emit. The two are orthogonal.

### 4. Search-friendly naming reframes — drop "translate to English", keep "clean canonical name"

**Decision.** Section 6 (Search-Friendly Naming) stays, but the rewrite drops any English-translation implication. Parser emits the food name in whatever language the user typed, in clean canonical form (drop adjectives like "small", "sour", "grilled" unless meaningful).

**Why.** Plan 2 shipped bilingual search (`food_service.py:108`) — `name_en ILIKE OR name_he ILIKE`. "ביצה" matches the Hebrew row directly, no translation needed. Forcing translation in the parser was a workaround for the Plan 1 single-language schema; that workaround is now harmful (mistranslations like "מעדן חלבון" → "Protein Bar" instead of "Protein Pudding").

### 5. Static unit-bucket table goes in `prompts/input_parser.md` directly, inverted by unit

**Decision.** Embed a table of `unit → list of foods` directly in the prompt as static text. Skip the gram-native foods entirely (they're the default). Single-coach POC assumption — the table mirrors `data/canonical_food_catalog.csv` where `default_unit != 'g'`.

**Why inverted.** The catalog has 28 non-gram foods across 8 unit buckets vs 65 gram-native foods. `unit → foods` reads as a parser rule (~150 tokens) instead of a 93-row lookup table (~1k tokens).

**Why static, not ContextSchema.** Zero runtime overhead, zero new code, mirrors how the rest of the prompt is loaded today. Drift risk (catalog changes → prompt goes stale) is small at POC scale because catalog updates are rare and intentional. A one-liner reminder in the prompt header tells future-Dolev to update the prompt when the catalog changes. Multi-coach migration to ContextSchema is logged for post-POC.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation

No foundation work — schemas, services, and node already in place from Plan 2.

### Phase 2: Core Implementation

Rewrite `prompts/input_parser.md` per the spec below. Single-file change.

### Phase 3: Integration

No integration work — `input_node.py` already reloads the prompt on next process start.

### Phase 4: Testing & Validation

- Run unit + integration test suites (must stay green; no schema change so no test edits expected).
- Manual smoke test via dev bot: send 5-8 messages covering each unit bucket + Hebrew quantifiers + no-quantity defaults.
- Defer eval dataset update to a separate task (eval target field shape changed, requires dataset rebuild).

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom.

### UPDATE `prompts/input_parser.md` — full rewrite

- **IMPLEMENT**: Replace the file contents with the new prompt (spec below).
- **PATTERN**: Mirror existing two-step structure. Keep numbered sub-rules under `IF action is LOG_FOOD`. Keep the Hebrew examples shape from commit `a56f23d`.
- **GOTCHA**: The file is loaded literally as the system message — no comments outside prompt content. Loaded once at module import, so changes take effect only on next dev server / process restart.
- **VALIDATE**: `uv run pytest tests/unit/test_input_parser.py -v` (must pass; schema unchanged so existing tests should remain green)

#### Prompt spec — section-by-section

**Header.** Add a one-line maintenance note above the existing first paragraph:

> *"Maintenance note: the unit-bucket table in Step 2.7 mirrors `data/canonical_food_catalog.csv` rows where `default_unit != 'g'`. When the catalog changes, update this table in the same PR."*

**Step 1: Identify Intent (Action).** Unchanged. All five actions (LOG_FOOD, QUERY_DAILY_STATS, LOG_PERSONAL_STATS, QUERY_FOOD_INFO, CHITCHAT) and their date-extraction sub-rules stay exactly as they are today.

**Step 2: Execute Strategy.**

**2.1 Decompose Meals.** Unchanged.

**2.2 Quantity & Unit Extraction (REPLACES current "Unit Normalization (Grams)").** New rule:

> *Extract `count` (numeric quantity) and `unit` (one of: `g, piece, slice, scoop, bottle, cup, tbsp, tsp, can`) for each food item.*
>
> *Choose `unit` as follows:*
> - *If the user states an explicit unit (grams, pieces, slices, etc.), use it directly.*
> - *Otherwise, look up the food in the unit-bucket table in Step 2.7. If the food is in the table, use the listed unit; the count is the number of those units mentioned (e.g., "2 eggs" → `count=2, unit=piece`).*
> - *If the food is NOT in the table, default to `unit="g"` and emit an estimated gram weight in `count`.*
> - *When in doubt, prefer `unit="g"` — grams always resolve safely.*
>
> *Examples:*
> - *"200g chicken" → `{count: 200, unit: "g"}`*
> - *"2 eggs" → `{count: 2, unit: "piece"}` (eggs in piece-bucket below)*
> - *"slice of bread" → `{count: 1, unit: "slice"}` (bread in slice-bucket below)*
> - *"1 cup rice" → estimate grams: `{count: 158, unit: "g"}` (rice not in unit table; user said cup but rice is gram-native; convert)*

**2.3 Hebrew Word-Form Quantifiers.** Keep the table and multi-item rule exactly as today. Only update the example outputs:

> *Examples (output format updated for the new schema):*
> - *"שלוש ביצים" (3 eggs) → `{count: 3, unit: "piece"}` — egg is in piece-bucket, see Step 2.7*
> - *"שתי פיתות" (2 pitas) → `{count: 2, unit: "piece"}`*
> - *"חמש פריכיות אורז" (5 rice cakes) → `{count: 5, unit: "piece"}`*
> - *"חצי כוס אורז" (half a cup of rice) → `{count: 79, unit: "g"}` — rice is gram-native; convert*

**2.4 Default Serving When No Quantity Given (REVISED).** Always emit grams when no quantity is mentioned, even for foods that have non-gram natural units:

> *When the user mentions a food without any quantity, ALWAYS emit `unit="g"` with a sensible default count:*
> - *Beverages (coffee, tea, juice): `count=240, unit="g"` (one cup equivalent)*
> - *Protein foods (chicken, fish, meat, egg, tofu, etc.): `count=100, unit="g"`*
> - *Whole fruit (banana, apple, orange): `count=120, unit="g"`*
> - *Anything else: a reasonable per-serving weight for that food in grams.*
>
> *Why grams as default: when the user is non-specific, guessing a non-gram unit is risky (it can fail the downstream resolver). Grams always resolve safely. Never return `count=0` or `count=1` with `unit="g"`.*

**2.5 Multi-Item Quantity Scoping.** Keep the rule. Update the example output:

> *Example: "log a banana and 100g rice" → Banana: `{count: 120, unit: "g"}` (default), Rice: `{count: 100, unit: "g"}` (explicit). NOT Banana: `{count: 100, unit: "g"}`.*

**2.6 Canonical Food Naming (REPLACES current "Search-Friendly Naming").** Reframe — drop the English-translation implication:

> *Emit `food_name` in clean canonical form, in the same language the user used. Drop unhelpful adjectives ("small", "sour", "grilled") unless they distinguish the food in the catalog.*
> - *"Small sour green apple" → `food_name: "apple"`*
> - *"Grilled chicken breast" → `food_name: "chicken breast"`*
> - *"ביצה קשה" → `food_name: "ביצה"` (search is bilingual — no need to translate)*
> - *"מעדן חלבון" → `food_name: "מעדן חלבון"` (do NOT translate; bilingual search will match name_he directly)*

**2.7 Unit-Bucket Reference Table (NEW SECTION).** Static table of foods with non-gram natural units:

> *Use this table to choose `unit` for known foods. Foods NOT listed default to `unit="g"`.*
>
> ```
> piece:
>   - egg / ביצה
>   - protein bar / חטיף חלבון
>   - protein pudding / מעדן חלבון
>   - white pita / פיתה לבנה
>   - bread roll / לחמנייה
>   - laffa / לאפה
>   - rice cake / פריכית אורז
>   - apple / תפוח
>   - banana / בננה
>   - dates / תמרים
>   - Para chocolate cubes / קוביות פרה
>   - Kinder Bueno / קינדר בואנו
>
> slice:
>   - white bread / לחם לבן
>   - yellow cheese 9% / גבינה צהובה 9%
>   - yellow cheese regular / גבינה צהובה רגילה
>
> scoop:
>   - whey protein / וויי
>
> bottle:
>   - Yotvata Pro / יטבתה פרו
>   - beer / בירה
>
> cup:
>   - protein yogurt / יוגורט חלבון
>   - black coffee / קפה שחור
>   - tea / תה
>
> tbsp:
>   - mayonnaise / מיונז
>   - tahini raw / טחינה גולמית
>   - olive oil / שמן זית
>
> tsp:
>   - sugar / סוכר
>   - peanut butter / חמאת בוטנים
>
> can:
>   - tuna in water / טונה במים
>   - tuna in oil / טונה בשמן
> ```

**Section "IF action is LOG_PERSONAL_STATS, QUERY_DAILY_STATS, QUERY_FOOD_INFO, or CHITCHAT".** Unchanged.

**Output Format section.** Update the field list to match the new schema:

> *Response must be a valid JSON object matching the `FoodIntakeEvent` schema.*
> - *`action`: One of the standard Enum values above.*
> - *`items`: List of food items (only for LOG_FOOD). Each item has `food_name`, `count`, `unit`, `original_text`.*
> - *`meal_type`: Breakfast/Lunch/Dinner/Snack (optional).*
> - *`consumed_at`: Date and time the food was consumed (optional).*

---

## TESTING STRATEGY

### Unit Tests

`tests/unit/test_input_parser.py` — already parameterized over the new `count`/`unit` schema (Plan 2 work). Must remain green after the prompt rewrite. No new tests required for this plan (prompt-only change; Pydantic schema is the contract gate).

### Manual Smoke Tests (post-prompt deploy)

Run the dev bot in polling mode (`POLLING_MODE=true`), send the following and verify the parser output in `langgraph dev` logs:

| Input | Expected `{count, unit}` |
|---|---|
| `200g chicken` | `{200, g}` |
| `2 eggs` | `{2, piece}` |
| `שתי ביצים` | `{2, piece}` |
| `slice of bread` | `{1, slice}` |
| `a banana` | `{120, g}` (no quantity → default) |
| `chicken` | `{100, g}` (no quantity → default) |
| `1 cup rice` | `{158, g}` (rice not in table → grams) |
| `שלוש פריכיות אורז` | `{3, piece}` (rice cakes ARE in table) |
| `1 scoop whey` | `{1, scoop}` |
| `מעדן חלבון` | `{1, piece}` (in table; default count=1 for piece-bucket) |

### Eval Update (FOLLOW-UP TASK, NOT PART OF THIS PLAN)

`notebooks/evals/eval_input_parser_hebrew.py` — dataset target field changed from `amount_g` to `(count, unit)`. Dataset rebuild + re-run is a separate task tracked in the pointers doc. Don't gate this PR on it; gate the merge on smoke tests.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

The file is markdown — no linter. Eyeball pass for:
- Section header consistency
- No stray `# Notes for Claude:` style commentary
- All Pydantic field names match `src/schemas/input_schema.py`

### Level 2: Unit Tests

```bash
uv run pytest tests/unit/test_input_parser.py -v
uv run pytest tests/unit/ -v
```

### Level 3: Integration Tests

```bash
uv run pytest tests/integration/ -v
```

### Level 4: Manual Validation

```bash
# Local dev bot in polling mode (separate terminal)
POLLING_MODE=true uv run python -m bot.gateway

# Send the smoke-test inputs from the table above via Telegram
# Watch langgraph dev logs for parser output shape
uv run langgraph dev
```

---

## ACCEPTANCE CRITERIA

- [ ] `prompts/input_parser.md` updated per the section-by-section spec above
- [ ] All 5 locked decisions visibly reflected in the prompt text
- [ ] Unit-bucket table contains exactly the 28 non-gram foods from `data/canonical_food_catalog.csv`
- [ ] `uv run pytest tests/unit/` passes (no regressions)
- [ ] `uv run pytest tests/integration/` passes (no regressions)
- [ ] Manual smoke tests above all produce the expected `{count, unit}` shapes
- [ ] Maintenance note about catalog sync is in the prompt header

---

## COMPLETION CHECKLIST

- [ ] Single-task plan — prompt rewrite executed in one edit
- [ ] Validation passed at Levels 1-4
- [ ] Smoke test results captured in commit log
- [ ] Plan 3b (`macro_estimation.md` rewrite) plan kicked off
- [ ] Architectural follow-ups confirmed captured in `brain/planning/parser-architectural-followups.md`

---

## NOTES

**Why this is a small plan.** Prompt-only change, single file, schema already in place. The "implementation" is one Edit call. The plan exists to lock the design decisions explicitly so future-Dolev (and any execution agent) understands *why* the prompt looks the way it does — not because the work itself is complex.

**Why no "Out of Scope" section.** Per Dolev's instruction (2026-04-20), follow-up architectural work is logged in the brain (`brain/planning/parser-architectural-followups.md`) rather than in plan-doc out-of-scope sections. Plan stays tight; brain captures longer-horizon thinking.

**Confidence on one-pass execution.** 9/10. The only risks are (a) drift between the prompt's unit-bucket table and the actual catalog CSV (mitigated by the maintenance note), and (b) the LLM occasionally emitting a unit that's in the Literal set but not in the table (e.g., emitting `unit="cup"` for "cup of rice" because the user said "cup", even though rice is gram-native) — that case fails the resolver gracefully and surfaces as a HITL retry, not a silent miscalculation.
