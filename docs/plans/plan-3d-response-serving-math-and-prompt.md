# Plan 3d — Response Node: Serving Math + Prompt Rewrite + Audit Fixes

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

This plan bundles three intertwined pieces of work into one response-node pass:

1. **Option Y — surface `category`/`tag`/`serving_amount_g` in the daily log injection.** Chain the JOIN (`daily_logs` → `food_items` → `coach_food_mappings`) through the service layer, the serialization helper, the `ContextSchema.daily_log_today` dicts, and the `_format_daily_log` renderer — so the response LLM sees category per log line instead of guessing it from food names.

2. **Plan 3d prompt rewrite** (`prompts/response_generator.md`) — four targeted additions from the pointers doc:
   - Coach voice with **serving math** over category-grouped totals
   - Reference `tag` (lean/medium/fatty) in recommendations
   - Handle `UNIT_MISMATCH` error strings gracefully (don't leak technical prefix)
   - Budget-reasoning template (= audit Fix #6)

3. **Bundled audit fixes** (all land in the same prompt rewrite since they all touch this file):
   - **Fix #4** — Language consistency ("never mix Hebrew/English in the same reply")
   - **Fix #5** — Empty-log coach-voice opener (greet + reference target + invite first meal)
   - **Fix #6** — Budget reasoning = same as pointers item 4 above

This is **Plan 3d of 5** in the food catalog prompt-rewrite trilogy:

| Sub-plan | Scope | Status |
|---|---|---|
| Plan 3a | `prompts/input_parser.md` rewrite + unit-bucket table | **Shipped** |
| Plan 3b | `prompts/macro_estimation.md` rewrite | **Shipped** |
| Plan 3c | `prompts/agent_selection.md` rewrite | **Shipped** |
| **Plan 3d (this doc)** | `prompts/response_generator.md` + daily-log-enrichment code chain + audit Fixes #4/#5/#6 | Ready to execute |
| Plan 3e | `prompts/confirmation_parser.md` + `ItemEdit` schema extension | Pending |

## User Story

As **Dolev** (coach + only trainee during POC),
I want the bot's responses to reason over actual servings per category (protein/carb/free/free_calories) drawn from today's log, recommend lean vs fatty proteins based on meal context, handle unit-mismatch errors in a coach voice, open empty-log sessions with a proper greeting, and never mix languages,
So that the bot finally does the serving math it's been faking — my brother and the future coach demo see responses that read like a coach, not like a macro calculator.

## Problem Statement

The response node has three concurrent gaps:

**1. Serving math is vibes-based.** The prompt already states "1 protein serving = 20g complete protein; 1 carb serving = 50g carbs" — but the daily log injected into the prompt (`_format_daily_log`) renders each entry as `{amount}g — {cals} kcal, {protein}g, {carbs}g, {fat}g` with no category signal. The LLM guesses category from food names. Works for "chicken" (obvious protein), fails silently on "protein yogurt" (renders as dairy-calorie line, gets miscounted), "cottage cheese" (sometimes carb, sometimes protein depending on the LLM's mood), and any estimated food where the name is foreign or ambiguous.

**2. Prompt hasn't absorbed Plan 2 metadata.** `tag` (lean/medium/fatty) is now a first-class field on `coach_food_mappings`, but the response prompt doesn't use it for recommendations. Post-workout advice today just says "lean protein"; it can't translate that to "prefer `tag=lean` candidates when the log shows a post-workout gap".

**3. Error strings leak.** When `resolve_amount_g` raises, the error `"Unit mismatch: user gave 'piece', food 'Bread' expects 'slice'"` propagates through `processing_results[i].message` into the Context JSON. The response prompt has no rule to detect this — the LLM tends to either parrot the string or invent its own "something went wrong, try again." Neither is a coach voice.

**Plus three audit findings from the 2026-04-17 bot UX audit** (`brain/planning/bot-ux-audit-2026-04-17.md`):
- **Fix #4** — English words like "servings" leak into Hebrew replies.
- **Fix #5** — When today's log is empty, responses drop into neutral confirmation mode instead of opening with a coach voice.
- **Fix #6** — Given a loaded context (plan + log + time), the LLM doesn't compute remaining budget or condition recommendations on time-of-day. Confirmed in the 2026-04-17 dogfood trace.

All four fixes (pointers item 4 / Fix #6 is the same item) are response-prompt edits. Bundling them avoids re-loading the same file-level context four times and lets Fix #6 depend naturally on the new serving-math infrastructure.

## Solution Statement

Three code changes to surface coach-method metadata through the daily-log injection chain, followed by a structured prompt rewrite that uses that metadata.

**Code chain (Option Y):**
1. `QueriedLog` TypedDict gains three Optional fields (`category`, `tag`, `serving_amount_g`) — backward-compatible (Optional = `None` default). Keeps stats_node usage unchanged.
2. `daily_log_service` adds `get_logs_by_date_with_mappings(session, user_id, target_date, coach_id)` — a LEFT JOIN variant returning `list[(DailyLog, Optional[CoachFoodMapping])]`. Existing `get_logs_by_date` stays untouched (used by stats_node, keeps its current shape).
3. `_serialize_log` gains an optional `mapping` parameter. When present, the returned dict carries the three new fields. When absent, the dict matches today's shape. `get_todays_logs_serialized` switches to the new enriched function; serialized dicts now carry `category`/`tag`/`serving_amount_g`.
4. `_format_daily_log` in `response_node.py` gains a two-part render: (a) each log line includes `[category,tag]` when present; (b) a trailing "Today's totals by category" block aggregates servings per category so the LLM doesn't have to sum integers in its head.

**Prompt rewrite (`response_generator.md`):**
1. **Tone & format** — add explicit language consistency rule (Fix #4).
2. **Hard rules** — add UNIT_MISMATCH handling rule (detect `"Unit mismatch:"` prefix, produce coach-voice retry in user's language).
3. **New section: Reading the log** — teach category-grouped serving counting with the exact conventions ("1 protein serving = 20g complete protein; 1 carb serving = 50g carbs"), reference the "Today's totals by category" block the renderer emits, give explicit budget-reasoning template.
4. **Protein section** — reference `tag` for lean/fatty recommendations (e.g., post-workout → prefer tag=lean).
5. **New section: Empty-log opener** (Fix #5) — when the log line shows "Nothing logged yet today", open with greeting + reference today's target + invite first meal.

No ItemEdit schema changes, no migration, no new dependencies.

## Feature Metadata

**Feature Type**: Enhancement (bundled prompt rewrite + service-layer enrichment)
**Estimated Complexity**: Medium — 4 source files, 1 prompt file, 2 test files touched. No migration. No schema changes. All additive.
**Primary Systems Affected**: `src/agents/state.py`, `src/services/daily_log_service.py`, `src/agents/nodes/response_node.py`, `prompts/response_generator.md`
**Dependencies**: Plan 1 (schema + `coach_food_mappings` table) and Plan 2 (service layer two-table consumption) both shipped.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: YOU MUST READ THESE BEFORE IMPLEMENTING

**Source (to modify):**
- `src/agents/state.py` (lines 38-53) — `QueriedLog` TypedDict. Extend with three Optional fields. Do NOT change existing field types.
- `src/services/daily_log_service.py` (lines 109-129) — `get_logs_by_date` (keep as-is for stats_node). Lines 163-200 — `_serialize_log` + `get_todays_logs_serialized`. Mirror the Plan 2 `search_food_items` LEFT JOIN pattern from `src/services/food_service.py:108-128` for the new enriched query.
- `src/models.py` (lines 35-69 DailyLog, lines 110-140 CoachFoodMapping) — the JOIN targets. Note `DailyLog.food_id` is `Optional[UUID]` (logs may exist without a food linkage — FK set to `ON DELETE SET NULL` per Plan 1 notes).
- `src/agents/nodes/response_node.py` (lines 39-62 `_format_daily_log`, lines 72-115 `_build_context`) — renderer + JSON context builder. Only `_format_daily_log` needs changing.
- `prompts/response_generator.md` (entire file, 196 lines) — the prompt rewrite target. Most sections stay intact; surgical additions detailed under "Prompt Spec" below.

**Source (reference only, do NOT modify):**
- `src/services/food_service.py` (lines 95-153) — the `search_food_items` LEFT JOIN pattern to mirror. Note the `OUTER JOIN coach_food_mappings ON food_id = ... AND coach_id = ...` structure.
- `src/agents/state.py` (lines 86-109) — `MacroResult` TypedDict. Reference for what fields already carry category/tag in the pre-commit flow. The post-commit daily log entries need to gain the same fields.
- `src/context.py` (lines 34-52) — `ContextSchema.daily_log_today: list[dict]`. Dicts are untyped here, so adding new fields doesn't require schema changes at this layer.
- `src/agents/nodes/stats_node.py` — consumes `get_logs_by_date` (not the new enriched function). Enrichment is out of scope for the stats path; Optional fields on `QueriedLog` allow both paths to coexist.
- `src/config.py` — `DEFAULT_COACH_ID` constant. Needed for the JOIN's `coach_id` filter.
- `bot/gateway.py` — calls `get_todays_logs_serialized` to populate `ContextSchema.daily_log_today`. No change needed (service helper is swapped in place).

**Tests to update:**
- `tests/unit/test_response_node.py` — existing tests mock the LLM; if any fixture asserts on log-format strings, update them to include category/tag.
- `tests/integration/test_daily_log_model.py` or similar — add integration coverage for `get_logs_by_date_with_mappings`.
- `tests/conftest.py` (lines vary) — fixtures already seed `FoodItem + CoachFoodMapping` pairs per Plan 2 conftest work; no new fixture needed.

### New Files to Create

None. All changes are additive to existing files.

### Relevant Documentation

- `brain/planning/food-catalog-plan-3-pointers.md` — design rationale for Plan 3 trilogy
- `brain/planning/bot-ux-audit-2026-04-17.md` — origin of audit Fixes #4/#5/#6
- `commit_logs/2026-04-13_20-15-00_feat-nutrition-plan-injection.md` — how `nutrition_plan` gets into the response prompt (the pattern daily_log_today mirrors)
- `commit_logs/2026-04-17_11-54-54_feat-daily-log-injection-and-israel-tz.md` — original daily-log-injection shipment; this plan extends it

### Patterns to Follow

**Service-layer LEFT JOIN pattern** (mirror from `food_service.py:108-128`):

```python
stmt = (
    select(FoodItem, CoachFoodMapping)
    .outerjoin(
        CoachFoodMapping,
        (CoachFoodMapping.food_id == FoodItem.id)
        & (CoachFoodMapping.coach_id == coach_id),
    )
    .where(...)
)
rows = (await session.execute(stmt)).all()
return [(r[0], r[1]) for r in rows]
```

**Serialization pattern** (mirror from `_serialize_food_candidate` in `food_service.py:240-257`):

```python
def _serialize_log(log: DailyLog, mapping: Optional[CoachFoodMapping] = None) -> dict:
    """Additive serialization — existing callers still get the old shape."""
    base = { ...existing fields... }
    if mapping is not None:
        base["category"] = mapping.category
        base["tag"] = mapping.tag
        base["serving_amount_g"] = mapping.serving_amount_g
    return base
```

**Renderer pattern** (`_format_daily_log` in `response_node.py:39-62`) — keep the existing line shape, append the annotation when present, add a trailing totals-by-category block.

**Prompt structure** — mirror the Plan 3a/3b/3c style: numbered rules, Hebrew + English examples where language-sensitive, code-block snippets for templates the LLM should emit verbatim.

---

## LOCKED DESIGN DECISIONS

Decided during the 2026-04-20 design call. Document these in the final commit.

### 1. Option Y, additive-only.

**Decision.** Chain category/tag/serving_amount_g from DB to prompt via a NEW enriched service function. Do NOT change existing `get_logs_by_date` or `_serialize_log(log)` signatures. Keep `QueriedLog` fields Optional.

**Why.** Stats path (`stats_node` → `daily_log_report`) is not in scope, works fine without enrichment. Keeping existing signatures untouched means no regression risk on the stats path. Optional fields on `QueriedLog` let the same TypedDict serve both populated (from response path) and non-populated (stats path) data.

### 2. Bundle Plan 3d + audit Fixes #4/#5/#6 into a single pass.

**Decision.** All four prompt-level changes ship together in one `response_generator.md` rewrite commit.

**Why.** Same file, same mental context. Fix #6 is literally the same item as pointers item 4 (budget reasoning template). Fixes #4 (language) and #5 (empty opener) are each ≤5 lines of prompt — not worth separate PRs.

### 3. Render the "Today's totals by category" block inside `_format_daily_log`.

**Decision.** The renderer (Python code), not the LLM, computes category-grouped totals (sum of grams, sum of kcal, sum of protein, number of servings where applicable). The LLM reads pre-computed totals instead of summing in prose.

**Why.** Deterministic. No token cost for the LLM doing integer math. Eliminates an entire class of hallucination ("you've had 2 protein servings" when it's actually 1.3). The LLM still reasons over the totals; it just doesn't compute them.

### 4. `servings` calculation uses coach-method constants, not per-food `serving_amount_g`.

**Decision.** Servings = `total_category_grams / CATEGORY_SERVING_SIZE`, where:
- `protein`: 20g protein → 1 protein serving
- `carb`: 50g carbs → 1 carb serving
- `free`: no serving concept (emit null, report grams only)
- `free_calories`: no serving concept; report kcal-against-budget (100 kcal = 1 unit of free budget)
- `forbidden_main`: same as free_calories per coach method

This aligns with the existing prompt line "1 protein serving = 20g complete protein; 1 carb serving = 50g carbs". Per-food `serving_amount_g` from the mapping is NOT used for the totals block (it's a per-meal signal, different purpose).

**Why.** Coach method is based on these two constants, not per-food serving counts. Summing per-food `serving_amount_g` would double-count (a protein yogurt serving is 150g, but its 20g protein is the actual serving count toward the daily target).

### 5. UNIT_MISMATCH detection: string-prefix match on `"Unit mismatch:"`.

**Decision.** The prompt teaches the LLM to detect the literal prefix `"Unit mismatch:"` in a FAILED item's `message` and produce a coach-voice retry in the user's language ("I couldn't match that unit for X — try grams or the natural unit").

**Why.** Cheap. No structured error type needed for POC. The error path is rare (~5-10% of items at most once Plan 3a's unit-bucket table is live). Follow-up to make it a structured enum is already logged in `brain/planning/parser-architectural-followups.md` under "Follow-up 1 — Parser retry loop".

### 6. No changes to `daily_log_report` (stats path).

**Decision.** The stats path still sees un-enriched `QueriedLog` dicts. Enriching stats is a follow-up.

**Why.** Scope containment. Response-node injection is the highest-leverage target — every message benefits. Stats queries are less frequent and the LLM can still reason over raw macros.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation — extend types and add enriched service function

Bottom-up: state TypedDict first, then service helpers, then node renderer, then prompt. Each layer depends on the layer below.

**Tasks:**
- Extend `QueriedLog` TypedDict with three Optional fields
- Add `get_logs_by_date_with_mappings` service function to `daily_log_service.py`
- Update `_serialize_log` signature to accept `Optional[CoachFoodMapping]`
- Update `get_todays_logs_serialized` to call the new enriched function

### Phase 2: Renderer — surface category in the prompt

**Tasks:**
- Update `_format_daily_log` to include `[category,tag]` annotation per line
- Add "Today's totals by category" block computed from the enriched dicts

### Phase 3: Prompt Rewrite

**Tasks:**
- Add language consistency rule to Tone & format
- Add UNIT_MISMATCH rule to Hard rules
- Insert new "Reading the log" section with serving math + budget template
- Update protein section to reference `tag` for recommendations
- Insert new "Empty-log opener" section

### Phase 4: Testing & Validation

**Tasks:**
- Update `tests/unit/test_response_node.py` fixtures to include category in log dicts where asserted
- Add `tests/integration/test_daily_log_service.py::TestEnrichedQuery` — cover both populated-mapping and missing-mapping cases
- Manual smoke test via dev bot — verify category lines appear in prompt (via `langgraph dev` logs)

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order. Tasks in the same phase can be interleaved; cross-phase order is strict.

### 1. UPDATE `src/agents/state.py`

- **IMPLEMENT**: Add three Optional fields to `QueriedLog` TypedDict: `category: Optional[str]`, `tag: Optional[str]`, `serving_amount_g: Optional[float]`.
- **PATTERN**: Mirror the existing Optional-field style in `QueriedLog` (e.g., `meal_type: Optional[str]`).
- **IMPORTS**: `Optional` already imported.
- **GOTCHA**: Keep existing field order. Add new fields at the end for diff cleanliness.
- **VALIDATE**: `uv run python -c "from src.agents.state import QueriedLog; q: QueriedLog = {'id':'x','food_id':None,'amount_g':1,'calories':1,'protein':1,'carbs':1,'fat':1,'timestamp':__import__('datetime').datetime.now(),'meal_type':None,'original_text':None,'category':None,'tag':None,'serving_amount_g':None}; print('OK')"`

### 2. ADD `get_logs_by_date_with_mappings` to `src/services/daily_log_service.py`

- **IMPLEMENT**: New async function, returns `list[tuple[DailyLog, Optional[CoachFoodMapping]]]`. Signature: `async def get_logs_by_date_with_mappings(session: AsyncSession, user_id: str, target_date: date, coach_id: uuid_mod.UUID = DEFAULT_COACH_ID) -> list[tuple[DailyLog, Optional[CoachFoodMapping]]]`.
- **PATTERN**: Mirror `search_food_items` from `src/services/food_service.py:108-128` — `select(DailyLog, CoachFoodMapping).outerjoin(CoachFoodMapping, (CoachFoodMapping.food_id == DailyLog.food_id) & (CoachFoodMapping.coach_id == coach_id)).where(DailyLog.user_id == ... & func.date(DailyLog.timestamp) == target_date).order_by(DailyLog.timestamp)`.
- **IMPORTS**: `from src.config import DEFAULT_COACH_ID`, `from src.models import CoachFoodMapping`.
- **GOTCHA**: LEFT OUTER JOIN, not inner. Some logs may have `food_id=None` (post-Plan-1 CASCADE SET NULL survivors) — those get `Optional[CoachFoodMapping] = None` naturally. Logs with `food_id` but no mapping for the coach also get `None`.
- **VALIDATE**: `uv run pytest tests/integration/test_daily_log_service.py -v -k enriched` (after Task 7 adds the test).

### 3. UPDATE `_serialize_log` in `src/services/daily_log_service.py`

- **IMPLEMENT**: Add `mapping: Optional[CoachFoodMapping] = None` parameter. When `mapping is not None`, extend the returned dict with three keys: `category`, `tag`, `serving_amount_g`. When `mapping is None`, the dict shape is unchanged from today.
- **PATTERN**: Same additive-dict style as `_serialize_food_candidate` in `food_service.py:240-257`.
- **IMPORTS**: `from src.models import CoachFoodMapping`.
- **GOTCHA**: Existing callers (`query_food_logs` tool, `get_logs_by_date`-based code paths) don't pass `mapping` → they still get the old shape. Only `get_todays_logs_serialized` switches to the new call path.
- **VALIDATE**: `uv run pytest tests/unit/test_daily_log_service.py -v` (existing tests must stay green).

### 4. UPDATE `get_todays_logs_serialized` in `src/services/daily_log_service.py`

- **IMPLEMENT**: Replace the `get_logs_by_date(...)` call with `get_logs_by_date_with_mappings(...)`. Iterate the returned tuples and call `_serialize_log(log, mapping)` for each.
- **PATTERN**: Straightforward swap — no signature change on the helper itself.
- **IMPORTS**: No new imports needed.
- **GOTCHA**: The KNOWN LIMITATION comment about timezone boundary (lines 193-196 of current file) carries over unchanged — still a follow-up, not in Plan 3d scope.
- **VALIDATE**: `uv run python -c "import asyncio; from src.services.daily_log_service import get_todays_logs_serialized; print('import OK')"`

### 5. UPDATE `_format_daily_log` in `src/agents/nodes/response_node.py`

- **IMPLEMENT**: Two changes.
  - (a) In the per-log loop, append `[category,tag]` when `log.get("category")` is truthy. Example: `- 08:30 — 200g chicken — 330 kcal, 62.0g protein, ... [protein,lean]`. If only category (no tag), emit `[protein]`. If no mapping, no annotation.
  - (b) After the per-log loop, append a "Today's totals by category" block aggregating: for each category found in the logs, sum amount_g, sum kcal, sum protein, sum carbs; compute protein servings (`sum_protein / 20`, rounded to 1 decimal) for `category=protein`; carb servings (`sum_carbs / 50`, rounded to 1 decimal) for `category=carb`; kcal-against-free-budget (`sum_kcal / 100`, rounded to 1 decimal) for `category=free_calories`; raw grams + kcal only for `free`, `forbidden_main`, `fat`.
- **PATTERN**: Keep the existing markdown-section shape (`## Today's Log\n-line\n-line`). Add a second section below: `## Today's Totals by Category`.
- **IMPORTS**: `from collections import defaultdict`.
- **GOTCHA**: Logs without category are STILL rendered in the per-log section; they're just excluded from the totals block (category=None → unknown → can't aggregate). Add a comment explaining this trade-off.
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v` (update fixtures in Task 8 as needed).

### 6. UPDATE `prompts/response_generator.md` — language consistency rule

- **IMPLEMENT**: In the `## Tone & format` section, after the existing "Match the user's language" bullet, add a sub-bullet: *"Never mix languages in the same reply. If the user writes in Hebrew, every word in your reply — including nutrition terms like 'servings' / 'מנות', 'protein' / 'חלבון', 'carbs' / 'פחמימות' — must be in Hebrew. Same for English in → English out."*
- **PATTERN**: Keep existing bullet style.
- **IMPORTS**: N/A (prompt file).
- **GOTCHA**: Don't duplicate — the existing "Match the user's language" line stays; the new rule is a refinement beneath it.
- **VALIDATE**: Reload prompt (`uv run python -c "from src.agents.nodes.response_node import _SYSTEM_PROMPT; assert 'Never mix languages' in _SYSTEM_PROMPT; print('OK')"`).

### 7. UPDATE `prompts/response_generator.md` — UNIT_MISMATCH hard rule

- **IMPLEMENT**: Add a new hard rule (numbered 6) in the `## Hard rules` section:
  > *6. **Handle UNIT_MISMATCH gracefully.** When a FAILED item's `message` starts with `"Unit mismatch:"`, don't parrot the technical string. Produce a coach-voice retry in the user's language: "I couldn't log `<food_name>` with the unit you used. Try grams (e.g., '200g') or the natural unit for that food (e.g., 'a slice', 'two pieces')."*
- **PATTERN**: Keep numbered list style.
- **GOTCHA**: The existing rule 2 ("Handle failures") stays — rule 6 is a specialization for unit-mismatch specifically.
- **VALIDATE**: Reload prompt, grep for "UNIT_MISMATCH" and "Unit mismatch:".

### 8. UPDATE `prompts/response_generator.md` — new "Reading the log" section

- **IMPLEMENT**: Insert a new H2 section between `## Read the plan before responding` and `## The method — mental model`:

  ```
  ## Reading the log

  The system injects a structured daily log block. Every entry may carry a `[category,tag]` annotation pulled from the coach's method. A "Today's Totals by Category" block below the line-items gives you pre-computed servings — do NOT recompute these; just read them and reason.

  ### Serving math conventions
  - 1 protein serving = 20g complete protein
  - 1 carb serving = 50g carbs
  - 1 unit of free-calorie budget = 100 kcal
  - `free`, `forbidden_main`, `fat` categories: no serving concept; report raw grams or kcal only

  ### Budget-reasoning template
  When the user asks "what should I eat?", "how much protein left?", "am I on track?":
  1. Read today's totals from the injected block.
  2. Compare to the plan's daily targets (protein/carb servings per phase, training vs rest).
  3. Compute the gap: `remaining = target - consumed`.
  4. Condition on time-of-day from the injected `Current time:` line:
     - Morning + far from target → "plenty of day left, don't front-load carbs"
     - Post-workout window + carb gap → "this is the main carb opportunity"
     - Evening + protein gap → "prioritize a high-protein meal before bed"
  5. Recommend specific food categories (and tag where applicable — e.g., post-workout → prefer tag=lean protein + simple carb).
  6. Never invent numbers. If the plan doesn't specify a target, say so.
  ```

- **PATTERN**: Standard H2 section. Keep code-block for the template.
- **GOTCHA**: Does NOT replace the existing "## The method — mental model" section. Read-log comes before the method doctrine; method doctrine stays.
- **VALIDATE**: Reload prompt, grep for "Reading the log", "Budget-reasoning template".

### 9. UPDATE `prompts/response_generator.md` — protein section `tag` reference

- **IMPLEMENT**: In `### Complete protein only`, append a sentence: *"When the log shows a `tag` annotation, use it for recommendations: `lean` preferred post-workout (fast digestion) and during cut phase; `fatty` acceptable at other times; `medium` is neutral."*
- **PATTERN**: Append to existing paragraph.
- **GOTCHA**: Don't rewrite the existing complete-protein doctrine; just add the tag layer.
- **VALIDATE**: Reload prompt, grep for "tag".

### 10. UPDATE `prompts/response_generator.md` — empty-log opener section

- **IMPLEMENT**: Insert a new H2 section between `## Time awareness` and `## When to escalate to the coach`:

  ```
  ## Empty-log opener

  When the injected daily log shows "Nothing logged yet today", the user hasn't logged a single entry. Unless the user's incoming message is itself a food log (in which case you're in normal confirmation mode), open with a coach voice:

  1. Greet briefly in the user's language.
  2. Reference today's target from the plan (protein servings and carb servings per the current phase and day type — training vs rest).
  3. Invite the first meal, ideally aligned with the time-of-day (morning → suggest protein-forward breakfast or fasting window if before wake+3h; later → whatever fits the gap).

  Keep it under 3 sentences. Do NOT fire this if the user's message already implies logging activity or a direct question — that's normal mode.
  ```

- **PATTERN**: Standard H2 section.
- **GOTCHA**: The "unless the user's message is itself a food log" clause is critical — otherwise the opener fires redundantly on the user's first log of the day.
- **VALIDATE**: Reload prompt, grep for "Empty-log opener".

### 11. UPDATE `tests/unit/test_response_node.py` — log-format fixtures

- **IMPLEMENT**: Audit existing fixtures / tests that construct log dicts. If any assert on the output of `_format_daily_log`, add `category` and `tag` fields to the input dicts and update expected output strings to include the annotations + totals block.
- **PATTERN**: Preserve existing AAA docstring structure from the test-engineering skill.
- **IMPORTS**: None new.
- **GOTCHA**: Tests that mock the LLM entirely (most of them) don't care about log content — they only care about graph plumbing. Only fixtures that inspect `_format_daily_log` output need updating.
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v`.

### 12. ADD integration test for `get_logs_by_date_with_mappings`

- **IMPLEMENT**: In the appropriate integration test file (likely `tests/integration/test_daily_log_service.py` or equivalent — grep for existing `get_logs_by_date` coverage), add a `TestEnrichedQuery` class with at least three cases:
  - Log with food_id + valid coach mapping → tuple has non-None mapping
  - Log with food_id but no mapping for the coach → tuple has None mapping
  - Log with no food_id (CASCADE SET NULL survivor) → tuple has None mapping
- **PATTERN**: Follow existing integration-test patterns from `tests/integration/test_food_service.py::TestCoachMappingJoin`.
- **IMPORTS**: Standard pytest async imports already in conftest.
- **GOTCHA**: The conftest fixture already seeds FoodItem + paired CoachFoodMapping per Plan 2 — leverage it.
- **VALIDATE**: `uv run pytest tests/integration/test_daily_log_service.py -v -k enriched`.

---

## TESTING STRATEGY

### Unit Tests

- `tests/unit/test_response_node.py` — keep LLM mocking. Only update fixtures if they assert on `_format_daily_log` output strings.
- No new unit tests for `get_logs_by_date_with_mappings` itself (it's a DB query — integration territory).

### Integration Tests

- `tests/integration/test_daily_log_service.py` (or discovered equivalent) — new `TestEnrichedQuery` class covering the three mapping states above.

### Manual Smoke Tests (post-deploy)

Run dev bot in polling mode, exercise:

| Scenario | Expected prompt behavior |
|---|---|
| Log "200g chicken", then ask "how much protein left?" | Prompt renders `[protein,lean]` on chicken line, "Today's Totals" shows protein grams + servings, reply quotes remaining correctly |
| Unit-mismatch: "3 pieces of bread" when bread is slice-native | Reply in coach voice, no `"Unit mismatch:"` leak |
| Hebrew user asks "כמה חלבון יש לי?" | Reply entirely in Hebrew, no English nutrition terms |
| First message of the day with no logs | Coach-voice opener referencing plan targets, invites first meal |
| Post-workout time, user asks "what should I eat?" | Reply references `tag=lean` preference + simple carb window |

### Edge Cases

- Empty log + user logs food → opener must NOT fire (normal confirmation mode wins per the rule clause)
- Log with `food_id=None` (CASCADE survivor) → rendered without annotation, excluded from totals-by-category
- Log with food but no coach mapping for DEFAULT_COACH_ID → rendered without annotation, excluded from totals
- All-category day (log has protein + carb + free + free_calories) → totals block renders all four buckets
- Single-category day → totals block renders just that bucket

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
uv run ruff check src/ tests/
uv run python -c "from src.agents.state import QueriedLog; from src.services.daily_log_service import get_todays_logs_serialized, get_logs_by_date_with_mappings; print('imports OK')"
uv run python -c "from src.agents.nodes.response_node import _SYSTEM_PROMPT, _format_daily_log; print(f'prompt: {len(_SYSTEM_PROMPT)} chars')"
```

### Level 2: Unit Tests

```bash
uv run pytest tests/unit/ -v
```

### Level 3: Integration Tests

```bash
uv run pytest tests/integration/test_daily_log_service.py -v
```

Full integration suite optional — user has indicated skipping is acceptable for prompt-adjacent changes.

### Level 4: Manual Validation

```bash
POLLING_MODE=true uv run python -m bot.gateway
# In another terminal:
uv run langgraph dev
# Send the smoke-test scenarios above via Telegram; watch langgraph dev logs for:
#   - [category,tag] annotations on log lines
#   - "Today's Totals by Category" block
#   - Coach-voice UNIT_MISMATCH handling
#   - Hebrew-only / English-only output purity
#   - Empty-log opener fires on zero-log first message
```

---

## ACCEPTANCE CRITERIA

- [ ] `QueriedLog` gains three Optional fields; existing stats path continues to work
- [ ] `get_logs_by_date_with_mappings` implemented, LEFT JOIN correct (three mapping states covered in integration tests)
- [ ] `_serialize_log` accepts optional `mapping`; existing callers still see old shape
- [ ] `get_todays_logs_serialized` uses the enriched function
- [ ] `_format_daily_log` emits `[category,tag]` per line + "Today's Totals by Category" block
- [ ] Totals block computes protein servings (/20g), carb servings (/50g), free-calorie units (/100kcal) per locked decision 4
- [ ] All 6 locked decisions visibly reflected
- [ ] Language-consistency rule in prompt
- [ ] UNIT_MISMATCH handling rule in prompt
- [ ] New "Reading the log" section with budget-reasoning template
- [ ] Protein section references `tag`
- [ ] New "Empty-log opener" section
- [ ] `uv run pytest tests/unit/` passes
- [ ] `uv run pytest tests/integration/test_daily_log_service.py` passes (focused integration)
- [ ] Manual smoke tests all produce expected shapes

---

## COMPLETION CHECKLIST

- [ ] All 12 tasks completed in order
- [ ] Per-task validation passed before moving on
- [ ] Full validation suite run at end
- [ ] Smoke tests captured in commit log
- [ ] Plan 3e (confirmation parser + ItemEdit schema) plan kicked off

---

## NOTES

**Why "Reading the log" comes before "The method".** The prompt's mental model is dense. Teaching the LLM how to read the injected log first grounds every downstream rule. Otherwise the LLM applies method doctrine to vibes-level log data and hallucinates numbers.

**Why the totals-block lives in Python, not in the LLM.** Deterministic math. Protein servings = sum_protein / 20 is a one-liner in Python; asking the LLM to do it on every message costs tokens AND introduces arithmetic errors. Reserve the LLM for reasoning (what the user should eat next), not for arithmetic.

**Why no structured error enum for UNIT_MISMATCH yet.** A proper fix (enum + i18n key + structured handler) is logged in `brain/planning/parser-architectural-followups.md`. For POC, string-prefix detection is sufficient. Revisit post-smoke-test.

**Scope containment.** Integration tests fully isolated to the new service function. No DB migration. No ContextSchema changes. No bot gateway changes. Roll-back is a revert of 4 files.

**Confidence score for one-pass execution: 8/10.** The serving-math computation logic in `_format_daily_log` is the highest-risk piece — careful handling of edge cases (missing category, missing tag, mixed categories, estimated foods with None mapping) is required. Tests cover the states but manual smoke test is still the true gate.
