# feat: food catalog Plan 3 — prompt trilogy (3a/3b/3c/3d) + daily-log serving-math enrichment

**Date:** 2026-04-21
**Commit:** `b562262`
**Branch:** `refine_prompts_and_evals`
**Plans:**
- [docs/plans/plan-3a-input-parser-prompt.md](../docs/plans/plan-3a-input-parser-prompt.md)
- [docs/plans/plan-3d-response-serving-math-and-prompt.md](../docs/plans/plan-3d-response-serving-math-and-prompt.md)

---

## Summary

Plan 3 of the food catalog refactor trilogy. Plans 3a / 3b / 3c are prompt-only rewrites aligning the LLM with the count/unit schema shipped in Plan 2 (commit `e27e8e9`). Plan 3d bundles a response-node prompt rewrite with the code chain that surfaces coach-method metadata (`category`, `tag`, `serving_amount_g`) through the daily-log injection — so the response LLM can reason about servings deterministically instead of guessing category from food names.

This commit unblocks the bot end-to-end after Plans 1 and 2 shipped schema and code but left the LLMs unaware of the new shape. Bot was broken between 2026-04-19 and today because the parser still said "extract grams" while the schema expected `count`/`unit`.

---

## Plan 3a — `prompts/input_parser.md`

Full prompt rewrite. Per-section spec and locked decisions in `docs/plans/plan-3a-input-parser-prompt.md`.

- Drop the "MANDATORY: convert all quantities to grams" rule. Parser now emits `{count, unit}` natively.
- Static 8-bucket unit reference table (`piece`, `slice`, `scoop`, `bottle`, `cup`, `tbsp`, `tsp`, `can`) listing only the 28 non-gram catalog foods — bilingual (English + Hebrew). Foods not listed default to `unit="g"`.
- Default-to-grams when no quantity given (Option A). Rationale: non-gram guesses can fail the resolver (`resolve_amount_g` ValueError); grams always pass.
- Preserved Hebrew word-form quantifier table + multi-item scoping from commit `a56f23d` (big accuracy win, 61% → 79%). Only the output target changed (grams → count/unit).
- Dropped forced English translation — bilingual search (`search_food_items`) handles Hebrew directly via `name_he ILIKE`.
- **Opportunistic bug fix**: QUERY_FOOD_INFO now extracts food items. `nutritionist.py:23` routes both `LOG_FOOD` and `QUERY_FOOD_INFO` through `food_search`, but the old prompt returned `items=[]` for QUERY_FOOD_INFO → `food_search_node` short-circuited with a warning log and no DB lookup ever happened. Pre-existing bug surfaced during the rewrite review.

Architectural follow-ups (retry loop on UNIT_MISMATCH, ContextSchema injection of unit hints for multi-coach, full plan injection at the parser) logged in `brain/planning/parser-architectural-followups.md`.

---

## Plan 3b — `prompts/macro_estimation.md`

Teach the LLM to fill **all** MacroEstimation schema fields, not just macros. Previously the prompt only covered calories/protein/carbs/fat; name_en/name_he/category/tag/default_unit/default_unit_weight_g were undocumented.

Locked decisions:
- **Bilingual names** (required): estimator fills both languages; one matches user input, translate to the other in clean canonical form.
- **Category taxonomy** with examples per category: `protein` / `carb` / `free` / `free_calories` / `forbidden_main` / `fat` (rarely used). Null when uncertain.
- **Protein `tag` thresholds** — fat-based, grounded in the catalog: `lean` ≤ 7g fat/100g, `medium` 7–15g, `fatty` > 15g. Proteins only; null otherwise.
- **`default_unit` rule** — emit when the food has an obvious natural unit (egg → piece, bread → slice); null (= gram-native) otherwise.
- Macro rules unchanged (1-decimal round, amount in grams upstream, values for the specific amount not per-100g).

Stakes reminder baked into the prompt: the LLM's output is persisted to the catalog via `commit_node` + `create_food_item` for every future log of the same food.

---

## Plan 3c — `prompts/agent_selection.md`

Small but sharp rewrite.

- Fix UUID-not-Integer description in output format (was "Integer ID" after UUID migration in Phase 3).
- Explicitly teach the `[category,tag]` annotation shape that `selection_node.py:54-67` already emits per candidate.
- New "explicit user qualifiers" heuristic — when the user says "lean chicken" / "חזה רזה", prefer `tag=lean`; "fatty cut" / "שומני" → `tag=fatty`; "raw meat" / "נא" → raw variant; "free vegetable" → `category=free`.
- Preserved existing heuristics (whole over processed, cooked over raw, generic over specific) with cleaned-up examples to match the current 93-row catalog.

---

## Plan 3d — `prompts/response_generator.md` + code chain

The biggest sub-plan. Combines Option Y code changes (surface category/tag in the daily log injection), the response prompt rewrite (pointers-doc items), and three bundled audit fixes (#4 language consistency, #5 empty-log opener, #6 budget reasoning = same as pointers item 4).

Full spec + locked decisions in `docs/plans/plan-3d-response-serving-math-and-prompt.md`.

### Code

- **`src/agents/state.py`** — `QueriedLog` TypedDict gains three Optional fields: `category: Optional[str]`, `tag: Optional[str]`, `serving_amount_g: Optional[float]`. Backwards compatible; stats path (`stats_node` → `daily_log_report`) unchanged.
- **`src/services/daily_log_service.py`**:
  - New `get_logs_by_date_with_mappings(session, user_id, target_date, coach_id=DEFAULT_COACH_ID)` — LEFT OUTER JOIN `daily_logs` ↔ `coach_food_mappings` scoped to `coach_id`. Returns `list[(DailyLog, Optional[CoachFoodMapping])]`. Mirrors the `search_food_items` JOIN pattern from `food_service.py:108`.
  - `_serialize_log(log, mapping=None)` — additive parameter. When `mapping` is present, the returned dict gains `category`/`tag`/`serving_amount_g`. When absent, shape is identical to pre-Plan-3d. Keeps `query_food_logs` tool and any direct-call site unchanged.
  - `get_todays_logs_serialized` swapped to call the new enriched function — 2-line change, no external signature change, so `bot/gateway.py` doesn't know anything changed.
- **`src/agents/nodes/response_node.py`**:
  - `_format_daily_log` per-line render appends `[category,tag]` when present (or `[category]` alone when tag is null). Legacy logs without category render without annotation.
  - New `_format_totals_by_category(logs)` helper — aggregates logs by coach-method category and renders a trailing `## Today's Totals by Category` block. Python computes protein servings (`sum_protein / 20`), carb servings (`sum_carbs / 50`), and free-calorie budget units (`sum_kcal / 100`). The LLM reads pre-computed numbers instead of doing arithmetic in prose — eliminates an entire class of hallucination. Uncategorized logs are excluded from the totals block. When no log has a category, the block is omitted entirely (preserves legacy shape).

### Prompt

- **NEW "Before every reply — do these in order" playbook** at the top. 6-step procedure: read time → read log + totals → read plan → pick one reply mode (UNIT_MISMATCH retry / generic failure / tight confirmation / budget template / empty-log opener / conversational) → apply time-of-day conditioning → compose in user's language. Turns the rest of the prompt into reference material the LLM consults from the playbook steps.
- **Language-consistency rule** (Fix #4) — sub-bullet under "Match the user's language": *"Never mix languages in the same reply. If the user writes in Hebrew, every word in your reply — including nutrition terms like 'servings' / 'מנות' — must be in Hebrew."*
- **UNIT_MISMATCH hard rule** — detect the literal `"Unit mismatch:"` prefix in a FAILED item's message and produce a coach-voice retry in the user's language. No raw `"Unit mismatch: user gave 'piece', food 'Bread' expects 'slice'"` leak.
- **NEW "Reading the log" section** — teaches the serving-math conventions (20g = 1 protein serving, 50g = 1 carb serving, 100 kcal = 1 free-calorie unit) and carries the 6-step budget-reasoning template (audit Fix #6).
- **NEW "Empty-log opener" section** (Fix #5) — when the injected log shows `Nothing logged yet today` AND the incoming message isn't itself a food log, open with greeting + today's target + invitation for first meal. Under 3 sentences.
- **Protein section** appended with tag-based recommendation guidance — `lean` preferred post-workout and during cut; `fatty` fine at other times; `medium` neutral.
- **REMOVED "Recomp phase"** subsection — the rule was "apply cut rules on rest days, bulk rules on training days," which is already what clean-bulk does (rest=neutral, training=surplus). The distinction didn't earn its lines.

---

## Config

**`src/config.py`** — `GLOBAL_MODEL` default switched to `gpt-5.4-nano` (was `gpt-4.1-nano`). Verified live via `get_llm_for_node('input_node').invoke(...)` round-trip. `.env LLM_MODEL_NAME` override still works per environment (Railway prod can stay on gpt-4.1-nano if desired).

Per-node model overrides not touched — all 6 nodes inherit `GLOBAL_MODEL` and only `temperature` varies in `NODE_CONFIGS`.

---

## Tests

- **+5 unit tests** in `tests/unit/test_response_node.py` covering:
  - `[category,tag]` annotation rendering
  - `[category]`-only annotation when tag is null (never `[carb,None]`)
  - Totals block computing protein servings (62g → 3.1) and carb servings (56g → 1.1)
  - Free-calories budget units rendering
  - Uncategorized logs excluded from totals block but still in per-log section
- **+5 integration tests** in `tests/integration/test_daily_log_service.py` under a new `TestEnrichedQuery` class:
  - Log with coach mapping → populated tuple
  - Log with food_id but no mapping for coach → None mapping
  - Log with `food_id=None` (CASCADE SET NULL survivor) → None mapping
  - Serialized log carries category/tag/serving_amount_g when mapping present
  - Serialized log omits those keys entirely when mapping absent (contract: absent, not present-with-None)
- **Fixed 2 false-positive assertions** in `test_response_node.py`. The prompt rewrite legitimately introduced strings (`processing_results`, `Nothing logged yet today`, `## Today's Log`) in the new checklist + empty-log-opener sections, which caused whole-prompt "not in" checks to false-positive. Fixed by slicing assertions to the injected-content region (between `## User Profile` and `Context JSON:`) or to the Context JSON block specifically.

---

## Validation

| Check | Result |
|---|---|
| `ruff check src/ tests/` | All checks passed |
| `uv run pytest tests/unit/` | **152/152 pass** (147 baseline + 5 new) |
| LLM round-trip on new model | `gpt-5.4-nano` → `'OK'` reply |
| Prompt file assertions | Never mix languages / Unit mismatch / Reading the log / Budget-reasoning template / Empty-log opener all present |

Integration suite + manual dev-bot smoke test intentionally deferred (Dolev's session-level direction; integration tests are expensive to run, manual smoke happens on the dev bot in Telegram).

---

## Known Breakage (Accepted)

None this time — Plan 2 shipped with "bot end-to-end broken until prompts land" as the accepted state. This commit lands those prompts, so the bot should work end-to-end again on the 5 smoke-test scenarios in the Plan 3d validation section.

---

## Next Steps

### Plan 3e — the final prompt

**Scope:** `prompts/confirmation_parser.md` rewrite + `ItemEdit` schema extension.

- Extend `ItemEdit` in `src/schemas/confirmation_schema.py` with `new_count: Optional[float]` and `new_unit: Optional[str]`. Either `new_amount_g` OR the count/unit pair is set, not both.
- Update `_apply_edits` in `confirmation_node.py` to branch on which field is set → pass to `calculate_food_macros` tool accordingly.
- Rewrite the prompt to accept unit-based edits: "change eggs to 3" → `new_count=3, new_unit="piece"` instead of `new_amount_g=150` (LLM guess). Also support pure grams: "change to 250g" → `new_amount_g=250`.
- HITL Hebrew copy refinement pass (exact wording for confirmation prompts post-smoke-test).

### Evals (follow-up tasks, not Plan 3e)

- Update `notebooks/evals/eval_input_parser_hebrew.py` — dataset target field changed from `amount_g` to `(count, unit)`. Dataset rebuild + re-run required.
- New macro-estimation eval — does the LLM emit sensible categories / default_units / weights? 20-30 off-menu foods with ground-truth labels.
- New unit-resolution eval — parser-level, given Hebrew + English phrasings, does the parser emit the correct count/unit tuple?

### Manual smoke test (before merging to main)

Run the dev bot in polling mode, exercise the Plan 3d 5-scenario table (log chicken + ask for protein remaining, unit-mismatch, Hebrew purity, empty-log opener, post-workout recommendation). Captured in the Plan 3d planning doc.

---

## Related Artifacts

- Brain note (deferred follow-ups): `brain/planning/parser-architectural-followups.md` (in the private brain repo)
- Plan 3d code-change spec: `docs/plans/plan-3d-response-serving-math-and-prompt.md`
- Plan 3a prompt-rewrite spec: `docs/plans/plan-3a-input-parser-prompt.md`
- Plan 2 that this unblocks: commit `e27e8e9`
- Plan 1 schema foundation: commit `bc0f6cc`
