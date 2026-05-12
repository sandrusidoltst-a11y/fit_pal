# Feature: Split `last_action` into `user_intent` + `pipeline_stage`, and route `QUERY_FOOD_INFO` past commit

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files.

## Feature Description

This PR delivers two coupled changes in one ship:

**Change 1 — State split (refactor, behavior-neutral).** `AgentState.last_action` is a single field doing two unrelated jobs:

1. **User intent** — what the user originally asked for: `LOG_FOOD`, `QUERY_FOOD_INFO`, `QUERY_DAILY_STATS`, `CHITCHAT`, `LOG_PERSONAL_STATS`. Set by the parser.
2. **Pipeline stage** — where the graph is in processing that intent: `SELECTED`, `NO_MATCH`, `AMBIGUOUS`, `AWAITING_CONFIRMATION`, `CONFIRMED`, `REJECTED`, `LOGGED`. Overwritten by every downstream node.

The refactor splits them into two independent state fields:

- **`user_intent: UserIntent`** — set once by `input_parser_node`, never overwritten in the same turn.
- **`pipeline_stage: PipelineStage`** — overwritten freely by `selection_node`, `calculate_macros_node`, `confirmation_node`, `commit_node`, `personal_stats_node`.

**Change 2 — `QUERY_FOOD_INFO` no longer routes through commit (bug fix, behavior change).** With `user_intent` now preserved end-to-end, `route_after_calculate_macros` can branch on it: `QUERY_FOOD_INFO` turns run `food_search → agent_selection → calculate_macros` (so the answer is grounded in real DB macros, not LLM hallucination) but **skip `confirmation` and `commit`** and go straight to `load_daily_context → response`. `response_node._build_context` surfaces the looked-up macros from `pending_confirmations` as `queried_foods` so the LLM answers nutrition questions with the DB values it just retrieved. Fixes TASKS.md Important #2 (`brain/planning/query-food-info-routing-latent-bug.md`).

`last_action` is kept alongside the new fields as a deprecated parallel field for one release so that **in-flight HITL-paused conversations** (whose Postgres checkpoints hold the old shape) resume safely. Removal is a tracked follow-up task.

## User Story

As a **FitPal user**
I want to **ask "how much protein is in an egg?" without being prompted to log an egg**
So that **the bot answers my nutrition questions from the DB without polluting my daily log**.

And as a **FitPal contributor**
I want to **read the user's original intent at any node, independently of pipeline progress**
So that **late-stage routers and the response generator can make decisions based on what the user actually asked for, not on which pipeline stage happens to have run last**.

## Problem Statement

**Problem A — Latent QUERY_FOOD_INFO silent-commit risk (TASKS.md Important #2).** When the parser classifies a message as `QUERY_FOOD_INFO`, today's routing sends it through the **full LOG pipeline** (`food_search → agent_selection → calculate_macros → confirmation → commit`). The pipeline ends with a HITL "Log this egg? yes/no" prompt for a question the user never asked as a log. If the user taps "yes" out of habit, the food is silently written to their daily log. The bug doesn't bite today only because three cancelling smells (parser emits empty items + agent_selection NO_MATCH + empty-batch shortcut in `confirmation_node`) coincide to skip the prompt. Fixing any one of those exposes the bug. See `brain/planning/query-food-info-routing-latent-bug.md`.

**Problem B — `last_action` conflates intent and stage, blocking the clean fix.** Three concrete symptoms:

1. **`route_after_calculate_macros` cannot route by intent.** By the time the router runs, `last_action` was overwritten from `QUERY_FOOD_INFO` → `SELECTED` → `AWAITING_CONFIRMATION`. The originating intent is gone — so any gate like `if last_action == "QUERY_FOOD_INFO"` cannot fire. This is what makes Problem A's fix architecturally awkward.

2. **`response_node._build_context` over-generalizes.** At `src/agents/nodes/response_node.py:162` the LOG flow is gated by `if last_action in ("LOG_FOOD", "LOGGED", "FAILED", "NO_MATCH", "SELECTED", "CONFIRMED", "REJECTED")` — six pipeline-stage values mashed with one intent value. The only reason this works today is that no other intent uses those stage names. Once QUERY_FOOD_INFO uses the same `SELECTED`/`NO_MATCH` stages, the same condition fires for both — and the LLM can't tell the difference.

3. **`NO_MATCH` is set by two different nodes for two different reasons** (`agent_selection_node` — search miss; `calculate_macros_node` — tool error). Both reasons end up in the same state field. Same string, different cause. Minor smell today, harder to disambiguate as more stages pile up. (**Out of scope for this PR** — see Out of Scope section.)

## Solution Statement

Split the field into two and add the routing gate in the same PR.

**Refactor (Change 1):**

- `user_intent` is written **once** by `input_parser_node` and never touched again in the turn.
- `pipeline_stage` is written by every downstream node that today writes `last_action` to a stage marker.
- `last_action` is **dual-written** for one release (every writer writes both old and new) so that paused HITL threads resume correctly.
- Readers (routers, response_node) read the new fields with a **legacy fallback** that derives intent/stage from `last_action` if the new fields are absent (covers checkpoints written before the deploy).

**Bug fix (Change 2):**

- `route_after_calculate_macros` gains a branch: `user_intent == "QUERY_FOOD_INFO"` → `load_daily_context` (skip `confirmation` and `commit`). LOG_FOOD continues to `confirmation` as today.
- `response_node._build_context` adds a `QUERY_FOOD_INFO` branch that surfaces `pending_confirmations` as `queried_foods` so the LLM has DB-grounded macros to answer with.
- `prompts/response_generator.md` gains a section: when `queried_foods` is present, answer the user's nutrition question with those macros — do NOT say "I logged" or "I'll log."
- `agent_selection_node` and `calculate_macros_node` are unchanged on the QUERY path. NO_MATCH on a query still triggers the estimation path inside `calculate_macros_node` — confirmed desired behavior ("how much protein in pomegranate seeds?" off-menu → LLM estimates → answer hedged as estimate).

## Feature Metadata

**Feature Type**: Refactor + Bug Fix (bundled)
**Estimated Complexity**: Medium-High
**Primary Systems Affected**:
- `src/agents/state.py` (type definitions, state shape)
- `src/agents/nutritionist.py` (3 router functions — `route_parser`, `route_after_selection`, `route_after_calculate_macros`)
- All 6 nodes that write `last_action` today (`input_node`, `selection_node`, `calculate_macros_node`, `confirmation_node`, `commit_node`, `personal_stats_node`)
- `src/agents/nodes/response_node.py` (`_build_context` reader — adds QUERY_FOOD_INFO branch)
- `prompts/response_generator.md` (rename `last_action` → `user_intent`; add `queried_foods` answering section)
- 14 test files in `tests/unit/`, `tests/integration/`
- `tests/graph_api/test_graph_flows.py` (new E2E test for QUERY_FOOD_INFO routing)
- 2 eval scripts in `notebooks/evals/`
**Dependencies**: None — no new libraries; pure internal refactor + routing change.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — YOU MUST READ THESE BEFORE IMPLEMENTING

#### State definitions

- `src/agents/state.py` (full file, lines 60-191) — Why: Contains `GraphAction` Literal (60-73) and `AgentState` TypedDict (157-191). The split happens here. Note `LogFoodSubState` (90-95) and `QueryStatsSubState` (97-107) — the substate pattern we're mirroring.
- `src/schemas/input_schema.py` (lines 8-14, 108-126) — Why: `ActionType` enum (the intent values) and the `UserIntent` Pydantic wrapper class. **Pre-refactor rename (Task 1)**: the Pydantic `UserIntent` becomes `UserIntentEvent` so the new Literal type can take the name `UserIntent`. Decision locked in Open Question #1.
- `src/schemas/selection_schema.py` (lines 7-11) — Why: `SelectionStatus` enum (`SELECTED`, `NO_MATCH`, `AMBIGUOUS`) — these are the pipeline-stage values set by selection node.

#### Routers

- `src/agents/nutritionist.py` (lines 22-37) — Why: `route_parser` and `route_after_selection` both read `last_action`. Each router needs to be classified — does it want intent or stage?
- `src/agents/nutritionist.py` (lines 39-43) — Why: `route_after_calculate_macros` does NOT currently read `last_action` (routes on `pending_food_items`). It does not change in this refactor, but it is the router that the follow-up QUERY_FOOD_INFO PR will modify.

#### Writer nodes

- `src/agents/nodes/input_node.py` (lines 73-105) — Why: Single setter of intent. Sets `last_action: result.action.value`. Will additionally set `user_intent` and `pipeline_stage="PENDING"`.
- `src/agents/nodes/selection_node.py` (lines 22-94) — Why: Sets `last_action` to `NO_MATCH`/`SELECTED` at 5 sites (lines 38, 45, 81, 88, 93). Writes pipeline stage only.
- `src/agents/nodes/calculate_macros_node.py` (lines 28-125) — Why: Sets `last_action="NO_MATCH"` on tool error (75) and `last_action="AWAITING_CONFIRMATION"` on success (123). Writes pipeline stage only.
- `src/agents/nodes/confirmation_node.py` (lines 115-193) — Why: Returns `Command(update=...)` with `last_action="CONFIRMED"` (149) and `last_action="REJECTED"` (177). Writes pipeline stage only. Note: `Command.update` is a dict, same shape as any node return.
- `src/agents/nodes/commit_node.py` (lines 14-103) — Why: Sets `last_action="LOGGED"` at line 101. Writes pipeline stage only.
- `src/agents/nodes/personal_stats_node.py` (lines 31-80) — Why: Sets `last_action="LOGGED"` at line 78. Writes pipeline stage only.

#### Reader node

- `src/agents/nodes/response_node.py` (lines 153-206) — Why: `_build_context` is the only consumer of `last_action` outside the routers. Currently dispatches on `last_action` mixed (line 162). Migration: dispatch on `user_intent` for which flow we're in, then optionally use `pipeline_stage` within the LOG_FOOD branch to distinguish in-progress vs. final.

#### Prompt referenced by name

- `prompts/response_generator.md` (line 27) — Why: contains the literal token `last_action`. The LLM contract is being updated; the prompt should reference `user_intent` instead.

#### Test infrastructure

- `tests/conftest.py` (lines 43-58) — Why: `basic_state` fixture has `"last_action": ""`. Extend with new fields and defaults.
- `tests/unit/test_state_consistency.py` (full file) — Why: Asserts every value of `ActionType`, `SelectionStatus`, plus `LOGGED` and HITL actions are present in `GraphAction`. Needs parallel assertions for `UserIntent` (matches `ActionType`) and `PipelineStage` (matches `SelectionStatus` + `LOGGED` + HITL).
- `tests/unit/test_state_substates.py` (full file) — Why: Exemplar of how the existing substate pattern is tested (always-write-both invariant). Mirror this style for the new fields.
- `tests/unit/test_response_node.py` (lines 41-160) — Why: 27 assertions on `last_action` — the biggest single migration target. The `_make_state(**overrides)` helper at lines 20-34 is the canonical state builder for these tests; extend its defaults to include the new fields.

#### Test files needing migration

All assert `result["last_action"] == "<value>"`:

- `tests/unit/test_input_parser.py` — 6 assertions on intent values (LOG_FOOD, CHITCHAT, QUERY_DAILY_STATS, QUERY_FOOD_INFO). These map cleanly to `user_intent`.
- `tests/unit/test_agent_selection.py` — 4 assertions on stage values (NO_MATCH, SELECTED). Map to `pipeline_stage`.
- `tests/unit/test_calculate_macros_node.py` — 4 assertions (3 on NO_MATCH, 1 in state setup). Map to `pipeline_stage`.
- `tests/unit/test_confirmation_node.py` — 2 assertions on `Command.update["last_action"]` (CONFIRMED, REJECTED). Map to `pipeline_stage`.
- `tests/unit/test_commit_node.py` — 1 assertion (LOGGED). Map to `pipeline_stage`.
- `tests/unit/test_personal_stats_node.py` — 2 assertions (LOGGED). Map to `pipeline_stage`.
- `tests/unit/test_multi_item_loop.py` — 3 hits: 2 assertions on AWAITING_CONFIRMATION (pipeline_stage), 1 state setup with `LOG_FOOD` (user_intent).
- `tests/unit/test_feedback_logic.py` — 2 assertions on NO_MATCH. Map to `pipeline_stage`.
- `tests/unit/test_feedback_integration.py` — 5 state-setup hits mixing intent and stage values. Update both fields.
- `tests/unit/test_response_node.py` — 27 hits, mostly state setup. The `_make_state` helper carries most of the load. See migration strategy in Phase 3.
- `tests/integration/test_log_yesterday_e2e.py` — 1 hit (state setup with CONFIRMED). Map to `pipeline_stage`.

#### Eval files

- `notebooks/evals/eval_input_parser_hebrew.py` (line 454) — Why: reads `result["last_action"]` as the evaluator's `"action"` output label. Update to read `user_intent`.
- `notebooks/evals/eval_input_parser.ipynb` (cell at line 273) — Same as above, notebook copy.

#### Bot gateway (NOT affected)

- `bot/gateway.py` (lines 137-142) — Reads thread `state.get("tasks", [])` but does NOT touch `last_action`. **Bot deploy is independent of this refactor.**

#### Docs / patterns

- `docs/patterns/state-schemas.md` — Why: documents `last_action` as a field in `AgentState`. Update the table at lines 45-56 to include `user_intent` and `pipeline_stage` (and mark `last_action` as deprecated for one release).
- `docs/adr/0004-schema-to-state-translation-ownership.md` — Why: the substate pattern this refactor extends. Especially the "Naming convention" section at lines 60. The new Literal types should follow analogous naming (`UserIntent` Literal, `PipelineStage` Literal).

#### Motivating background

- `brain/planning/query-food-info-routing-latent-bug.md` (full file) — Why: the latent bug whose fix depends on this refactor. Do NOT fix the bug in this PR — only refactor.

### New Files to Create

- `docs/adr/0005-split-user-intent-from-pipeline-stage.md` — Capture the decision: why split, alternatives considered (keep monolithic; rename only; use substate-as-discriminator), backward-compat strategy (dual-write + legacy fallback), revisit trigger.
- (No new source files. All changes are edits to existing files.)

### Relevant Documentation — READ BEFORE IMPLEMENTING

- LangGraph state docs (via `docs-langchain` MCP):
  - **Why**: Confirm that adding new TypedDict fields to `AgentState` does not require migration of existing checkpoints (LangGraph stores state as a dict — extra fields are tolerated when readers use `state.get("new_field")`). Use `mcp__docs-langchain__search_docs_by_lang_chain` with query "state schema TypedDict checkpoint" before writing the migration shim.
- LangGraph HITL / interrupt docs:
  - **Why**: Confirm that paused threads at `interrupt()` resume with their saved state shape, and that the resumed graph code reads whatever is in the saved state. This is the case we are designing the legacy fallback for.

### Patterns to Follow

#### Translator-per-boundary (ADR-0004)

The schema-layer Pydantic models (`UserIntent` wrapper, `LogFoodEvent`, etc.) translate **once** at `input_parser_node` into plain TypedDict slots in state. No reader imports schema classes. After this refactor, `input_parser_node` continues to be the sole translator from `ActionType` to the `UserIntent` Literal.

#### Substate naming triad (ADR-0004:60)

- Schema variants end in `Event` (`LogFoodEvent`).
- State slots are snake-case keys (`state["log_food"]`).
- Typed shapes are `<Action>SubState` (`LogFoodSubState`).

This refactor doesn't add a sub-state; it adds two top-level fields. But naming should still be consistent:
- **Field name (snake_case)**: `user_intent`, `pipeline_stage`.
- **Literal name (PascalCase)**: `UserIntent`, `PipelineStage`. The Pydantic class is renamed to `UserIntentEvent` (Task 1) so the Literal can take the natural name.

#### Node read/write convention (`docs/patterns/state-schemas.md`)

Nodes read via `state.get("key")` and return a partial dict of only changed keys. LangGraph merges the dict. For this refactor:

```python
# input_parser_node — sole writer of user_intent
return {
    "last_action": result.action.value,        # legacy, dual-written
    "user_intent": result.action.value,         # new
    "pipeline_stage": "PENDING",                # new
    ...
}

# selection_node — writes pipeline_stage only
return {
    "selected_food_id": result.food_id,
    "last_action": result.status.value,        # legacy, dual-written
    "pipeline_stage": result.status.value,     # new
}
```

#### Error Handling

No new error paths introduced. Defensive `state.get()` everywhere (project convention).

#### Logging Pattern

`structlog` calls in nodes today log `action=...` (e.g. `input_node.py:69`). These already log `result.action.value` which is the intent. They don't reference `state["last_action"]`. **No log queries break.** Optional: add `pipeline_stage=...` to log calls in selection/calculate/confirmation/commit/personal_stats nodes for observability — gate behind reviewer call, not required.

#### Test pattern (AAA + arrange/act/assert docstrings)

See `tests/unit/test_state_substates.py` for the canonical form — class-grouped, `arrange/act/assert` docstrings. Mirror for new tests in this refactor.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation — Type definitions and dual-write

Establish the new types and have every writer dual-write the old and new fields. Behavior unchanged; nothing reads the new fields yet.

**Tasks:**

- Rename Pydantic `UserIntent` → `UserIntentEvent` (Task 1) — clears the way for the Literal to take the `UserIntent` name.
- Add `UserIntent` and `PipelineStage` Literals to `state.py`.
- Add `user_intent` and `pipeline_stage` fields to `AgentState`.
- Keep `last_action: GraphAction` field; type-narrow `GraphAction` as `UserIntent | PipelineStage` if helpful, or leave as-is.
- Update every writer node (`input_node`, `selection_node`, `calculate_macros_node`, `confirmation_node`, `commit_node`, `personal_stats_node`) to write both the legacy `last_action` and the appropriate new field.
- Update `tests/conftest.py:basic_state` to include the new fields with sensible defaults (`"user_intent": ""`, `"pipeline_stage": ""`).
- Run unit tests; everything should still pass without modification (because we haven't changed any readers yet and the existing assertions still match the legacy field).

### Phase 2: Readers — Routers and response_node

Switch every reader to consult the new fields with a legacy fallback so paused-checkpoint conversations survive the deploy.

**Tasks:**

- Add legacy-fallback helpers (private to `state.py` or a new `src/agents/state_compat.py`):
  - `_intent_from_legacy(last_action) -> Optional[UserIntent]`: returns `last_action` if it's in the `UserIntent` literal set, else `None`.
  - `_stage_from_legacy(last_action) -> Optional[PipelineStage]`: returns `last_action` if it's in the `PipelineStage` literal set, else `None`.
- Update `route_parser` in `nutritionist.py:22-30` to read `state.get("user_intent") or _intent_from_legacy(state.get("last_action"))`.
- Update `route_after_selection` in `nutritionist.py:32-37` to read `state.get("pipeline_stage") or _stage_from_legacy(state.get("last_action"))`.
- Update `_build_context` in `response_node.py:153-206`:
  - Dispatch on `user_intent` for "which flow" (LOG_FOOD/QUERY_DAILY_STATS/CHITCHAT/...).
  - Within the LOG_FOOD branch, use `pipeline_stage` if needed for sub-routing (e.g., FAILED vs. LOGGED rendering).
  - Continue to expose `last_action` in the JSON context for one release (the LLM prompt still references it) — this is a low-cost compatibility belt.
- Update `prompts/response_generator.md:27` to reference `user_intent` instead of `last_action`. Update any sibling references.

### Phase 3: Tests — Migrate assertions and add new coverage

Migrate every test that asserts on `last_action` to also assert on the new fields, and add invariants the refactor introduces.

**Tasks:**

- Update `tests/unit/test_state_consistency.py` to assert `UserIntent` and `PipelineStage` Literals contain the right values (mirror the existing `GraphAction` assertions).
- For each writer test (`test_input_parser.py`, `test_agent_selection.py`, `test_calculate_macros_node.py`, `test_confirmation_node.py`, `test_commit_node.py`, `test_personal_stats_node.py`, `test_multi_item_loop.py`, `test_feedback_logic.py`, `test_feedback_integration.py`):
  - Keep the existing `last_action` assertion (verifies dual-write).
  - Add a parallel assertion on the new field (`user_intent` or `pipeline_stage`).
- For `test_response_node.py`:
  - Update `_make_state(**overrides)` helper (lines 20-34) to populate both new fields by default, derived from `last_action` if not given explicitly.
  - Existing 27 assertions on `parsed["last_action"]` continue to pass via the dual-write fallback in `_build_context`.
  - Add new tests: assert `_build_context` dispatches on `user_intent` for each flow.
- Update `tests/integration/test_log_yesterday_e2e.py:78` — state setup with `"last_action": "CONFIRMED"`. Add `"pipeline_stage": "CONFIRMED"`.
- Add new test file `tests/unit/test_intent_stage_invariants.py`:
  - `test_user_intent_immutable_through_pipeline`: simulate a multi-node sequence (input_parser → selection → calculate_macros → confirmation → commit), assert `user_intent` stays equal to the parser's value at every step.
  - `test_pipeline_stage_transitions_through_log_flow`: verify the expected stage progression PENDING → SELECTED → AWAITING_CONFIRMATION → CONFIRMED → LOGGED.
  - `test_legacy_checkpoint_routes_correctly`: build a state with only `last_action` populated (no `user_intent`/`pipeline_stage`), invoke `route_parser` and `route_after_selection`, assert the legacy fallback returns the correct destination.

### Phase 4: Route `QUERY_FOOD_INFO` past commit (the bug fix)

With `user_intent` now preserved end-to-end, add the gate that fixes Problem A.

**Tasks:**

- Update `route_after_calculate_macros` in `nutritionist.py:39-43` to branch on `user_intent`:
  - If items still pending → `food_search` (loop, unchanged).
  - Else if `user_intent == "QUERY_FOOD_INFO"` → `load_daily_context` (NEW — skip confirmation + commit).
  - Else → `confirmation` (LOG_FOOD path, unchanged).
- Add a `load_daily_context` destination to the conditional-edges map in the graph builder.
- Update `_build_context` in `response_node.py`: add a `QUERY_FOOD_INFO` branch that exposes `pending_confirmations` as `queried_foods` in the JSON context so the LLM can answer with DB-grounded macros.
- Update `prompts/response_generator.md`: add a section instructing the LLM that when `queried_foods` is present, the user asked a nutrition question — answer with those macros, do NOT use logging language ("I logged", "I'll log").
- Add E2E test in `tests/graph_api/test_graph_flows.py` for the QUERY_FOOD_INFO path: send "how much protein is in an egg?", verify no commit (DB unchanged), verify response references macros for the queried food.

### Phase 5: Evals, docs, follow-up tasks

Finish the migration trail outside the source tree.

**Tasks:**

- Update `notebooks/evals/eval_input_parser_hebrew.py:454` and `notebooks/evals/eval_input_parser.ipynb` cell:273 to read `result["user_intent"]` instead of `result["last_action"]`. Eval datasets (uploaded to LangSmith) are unaffected — the field is only used as an output label, not as a dataset input.
- Update `docs/patterns/state-schemas.md`:
  - Add `user_intent` and `pipeline_stage` to the AgentState table (lines 45-56).
  - Mark `last_action` as "deprecated; removal tracked in TASKS.md".
  - Add a short paragraph: "Intent and stage are two concerns; one is set once, the other is overwritten. See ADR-0005."
- Create `docs/adr/0005-split-user-intent-from-pipeline-stage.md` (template below in Notes).
- Add to `brain/TASKS.md` (Maintenance section):
  - **Remove `last_action` from AgentState** — after one release window (recommended: 2 weeks post-deploy). Steps: drop the field from state.py, remove dual-write in every writer node, remove legacy-fallback helpers in routers + response_node, remove backwards-compatible reads in tests. Source: this plan.
  - **NO_MATCH overload disambiguation** — split `pipeline_stage="NO_MATCH"` into `SELECTION_NO_MATCH` (set by `selection_node`) vs `MACRO_CALCULATION_FAILED` (set by `calculate_macros_node`). Currently same string, different cause. Source: this plan.
  - **QUERY_FOOD_INFO silent-commit fix** — follow-up PR on top of this refactor. Add `query_food_info` substate; gate `route_after_calculate_macros` (or add a new gate before `confirmation`) on `user_intent == "QUERY_FOOD_INFO"`. Source: `brain/planning/query-food-info-routing-latent-bug.md`.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### 1. RENAME Pydantic `UserIntent` → `UserIntentEvent`

- **IMPLEMENT**: Rename the wrapper class so the new Literal can take the natural name `UserIntent`. Three touchpoints:
  - `src/schemas/input_schema.py:108` — class declaration `class UserIntent(BaseModel):` → `class UserIntentEvent(BaseModel):`. Also update the docstring (lines 109-121) where `UserIntent` is mentioned as the wrapper's purpose.
  - `src/agents/nodes/input_node.py:14` — `from src.schemas.input_schema import (... UserIntent, ...)` → `... UserIntentEvent, ...`.
  - `src/agents/nodes/input_node.py:64` — `structured_llm = llm.with_structured_output(UserIntent)` → `structured_llm = llm.with_structured_output(UserIntentEvent)`.
- **PATTERN**: ADR-0004:60 naming triad — schema variants end in `Event`. The wrapper now follows the same convention.
- **GOTCHA**: This is purely a rename. No behavior change. Run `uv run ruff check src/schemas/input_schema.py src/agents/nodes/input_node.py` after the edit to catch any straggler reference. Search for `UserIntent\b` (word-boundary) across the repo to confirm no other site references the old name:
  ```bash
  grep -rn 'UserIntent\b' src/ tests/ notebooks/ | grep -v UserIntentEvent
  ```
  Expected: zero results after the rename (the new `UserIntent` Literal hasn't been added yet — that's Task 2).
- **VALIDATE**: `uv run pytest tests/unit/test_input_parser.py -v` — the parser tests exercise this code path and must stay green.

### 2. UPDATE `src/agents/state.py` — Add Literals and fields

- **IMPLEMENT**:
  - Add new Literals near the existing `GraphAction` (line 60):
    ```python
    UserIntent = Literal[
        "LOG_FOOD",
        "QUERY_FOOD_INFO",
        "QUERY_DAILY_STATS",
        "CHITCHAT",
        "LOG_PERSONAL_STATS",
    ]

    PipelineStage = Literal[
        "PENDING",
        "SELECTED",
        "NO_MATCH",
        "AMBIGUOUS",
        "AWAITING_CONFIRMATION",
        "CONFIRMED",
        "REJECTED",
        "LOGGED",
    ]
    ```
  - Add fields to `AgentState` (after line 183):
    ```python
    user_intent: UserIntent  # set once by input_parser; immutable for the turn
    pipeline_stage: PipelineStage  # overwritten by intermediate nodes
    # last_action stays for one release — see ADR-0005
    ```
  - Update the docstring at line 171 to document both new fields and mark `last_action` deprecated.
- **PATTERN**: Existing `GraphAction` Literal at lines 60-73; `AgentState` TypedDict at lines 157-191.
- **IMPORTS**: None new — `Literal` already imported.
- **GOTCHA**: Don't change the existing `GraphAction` type yet. Old `last_action` still uses it. Removing `GraphAction` is a follow-up task.
- **VALIDATE**: `uv run python -c "from src.agents.state import AgentState, UserIntent, PipelineStage; print('ok')"`

### 3. UPDATE `tests/conftest.py:basic_state` — Add new field defaults

- **IMPLEMENT**: Add two keys to the `basic_state` fixture dict (after line 52):
  ```python
  "user_intent": "",
  "pipeline_stage": "",
  ```
- **PATTERN**: Mirror the existing `"last_action": ""` empty-string default at line 52.
- **GOTCHA**: Empty string is intentional — matches existing `last_action` default, makes "field unset" detectable in tests.
- **VALIDATE**: `uv run pytest tests/unit/ -v --co | head -20` (collection still works)

### 4. UPDATE `src/agents/nodes/input_node.py` — Dual-write intent

- **IMPLEMENT**: At lines 92-105, extend the returned dict to include both new fields:
  ```python
  return {
      "pending_food_items": items,
      "last_action": result.action.value,           # legacy, dual-written
      "user_intent": result.action.value,            # NEW — set once per turn
      "pipeline_stage": "PENDING",                   # NEW — reset at turn start
      "processing_results": [],
      "query_logs": [],
      "pending_confirmations": [],
      "search_results": [],
      "selected_food_id": None,
      "log_food": log_food,
      "query_stats": query_stats,
  }
  ```
- **PATTERN**: input_node already follows the always-write-all-fields turn-reset convention (lines 96-104). Continue that pattern.
- **IMPORTS**: None new.
- **GOTCHA**: `PENDING` is a new Literal value not in the existing `GraphAction` union. That is by design — only `pipeline_stage` accepts it. Don't add it to `GraphAction`.
- **VALIDATE**: `uv run pytest tests/unit/test_input_parser.py -v`

### 5. UPDATE `src/agents/nodes/selection_node.py` — Dual-write stage

- **IMPLEMENT**: Update all 5 return points (lines 36-39, 42-46, 79-82, 86-89, 91-94) to add `"pipeline_stage": <same-value-as-last_action>`. Example for line 36-39:
  ```python
  return {
      "selected_food_id": None,
      "last_action": "NO_MATCH",
      "pipeline_stage": "NO_MATCH",
  }
  ```
  Do the same for lines 42-46 (`SELECTED`), 79-82 (`NO_MATCH`), 86-89 (`NO_MATCH`), and 91-94 (where it's `result.status.value` — duplicate that into both fields).
- **PATTERN**: Same field set; dual-write is mechanical.
- **GOTCHA**: Don't write `user_intent` from this node. Selection node has no business overwriting intent.
- **VALIDATE**: `uv run pytest tests/unit/test_agent_selection.py -v`

### 6. UPDATE `src/agents/nodes/calculate_macros_node.py` — Dual-write stage

- **IMPLEMENT**:
  - At line 71-77, add `"pipeline_stage": "NO_MATCH"`.
  - At line 120-125, add `"pipeline_stage": "AWAITING_CONFIRMATION"`.
- **PATTERN**: Same dual-write.
- **GOTCHA**: This is the node where the QUERY_FOOD_INFO follow-up will gate. Don't gate here in this PR. Pure dual-write only.
- **VALIDATE**: `uv run pytest tests/unit/test_calculate_macros_node.py -v`

### 7. UPDATE `src/agents/nodes/confirmation_node.py` — Dual-write stage in `Command.update`

- **IMPLEMENT**:
  - At line 147-154 (Command's update on confirm), add `"pipeline_stage": "CONFIRMED"` to the `update` dict.
  - At line 174-183 (Command's update on reject), add `"pipeline_stage": "REJECTED"` to the `update` dict.
- **PATTERN**: `Command(update=...)` accepts the same dict shape as a node return.
- **GOTCHA**: This node also has an early `Command(goto="load_daily_context")` at line 130 with no `update`. Don't add fields there — empty-batch shortcut leaves state untouched, that's fine.
- **VALIDATE**: `uv run pytest tests/unit/test_confirmation_node.py -v`

### 8. UPDATE `src/agents/nodes/commit_node.py` — Dual-write stage

- **IMPLEMENT**: At line 99-103, add `"pipeline_stage": "LOGGED"`.
- **PATTERN**: Same dual-write.
- **VALIDATE**: `uv run pytest tests/unit/test_commit_node.py -v`

### 9. UPDATE `src/agents/nodes/personal_stats_node.py` — Dual-write stage

- **IMPLEMENT**: At line 77-80, add `"pipeline_stage": "LOGGED"`.
- **PATTERN**: Same dual-write.
- **GOTCHA**: This node also leaves `user_intent` untouched (correct — parser already set it to `LOG_PERSONAL_STATS`).
- **VALIDATE**: `uv run pytest tests/unit/test_personal_stats_node.py -v`

### 10. VALIDATE Phase 1 complete — all unit tests still green

- **IMPLEMENT**: No code change. Run full unit suite.
- **VALIDATE**: `uv run pytest tests/unit/ -v` — every test should still pass since readers haven't moved yet.

### 11. ADD legacy-fallback helpers in `src/agents/state.py`

- **IMPLEMENT**: Add at module level (after the Literal definitions):
  ```python
  from typing import get_args

  _INTENT_VALUES = set(get_args(UserIntent))
  _STAGE_VALUES = set(get_args(PipelineStage))


  def intent_from_legacy(last_action: str | None) -> str | None:
      """Map legacy `last_action` → `user_intent` for pre-refactor checkpoints.

      Returns the value if it's a known UserIntent, else None. Used by routers
      and response_node during the deprecation window so paused HITL threads
      whose checkpoints predate this refactor still route correctly.
      """
      if last_action and last_action in _INTENT_VALUES:
          return last_action
      return None


  def stage_from_legacy(last_action: str | None) -> str | None:
      """Map legacy `last_action` → `pipeline_stage` for pre-refactor checkpoints."""
      if last_action and last_action in _STAGE_VALUES:
          return last_action
      return None
  ```
- **PATTERN**: Module-level helpers in state.py is fine — same file owns the type definitions and the legacy mapping. Alternative (new file `src/agents/state_compat.py`) is also fine, decide on style.
- **IMPORTS**: `from typing import get_args` (already in `tests/unit/test_state_consistency.py`).
- **GOTCHA**: These helpers must be **removed** when `last_action` is removed in the follow-up cleanup PR. Add a `# REMOVE WITH last_action — see TASKS.md` comment.
- **VALIDATE**: `uv run python -c "from src.agents.state import intent_from_legacy, stage_from_legacy; print(intent_from_legacy('LOG_FOOD'), stage_from_legacy('LOGGED'))"` → prints `LOG_FOOD LOGGED`.

### 12. UPDATE `src/agents/nutritionist.py:route_parser` — Read intent with fallback

- **IMPLEMENT**: At lines 22-30, change the read:
  ```python
  def route_parser(state: AgentState):
      from src.agents.state import intent_from_legacy
      intent = state.get("user_intent") or intent_from_legacy(state.get("last_action"))
      if intent == "LOG_FOOD" or intent == "QUERY_FOOD_INFO":
          return "food_search"
      elif intent == "QUERY_DAILY_STATS":
          return "stats_lookup"
      elif intent == "LOG_PERSONAL_STATS":
          return "personal_stats"
      return "load_daily_context"
  ```
- **PATTERN**: Conditional edge function reads state, returns string key.
- **GOTCHA**: This router cares about **intent**, not stage. Don't read `pipeline_stage`. The `or` short-circuit handles the legacy-checkpoint case.
- **VALIDATE**: `uv run pytest tests/unit/ -v -k "input_parser or routing"`

### 13. UPDATE `src/agents/nutritionist.py:route_after_selection` — Read stage with fallback

- **IMPLEMENT**: At lines 32-37:
  ```python
  def route_after_selection(state: AgentState):
      from src.agents.state import stage_from_legacy
      stage = state.get("pipeline_stage") or stage_from_legacy(state.get("last_action"))
      if stage in ["SELECTED", "NO_MATCH"]:
          return "calculate_macros"
      return "load_daily_context"
  ```
- **PATTERN**: Same conditional edge pattern.
- **GOTCHA**: This router cares about **stage** (was selection successful or not). Reads stage, not intent.
- **VALIDATE**: `uv run pytest tests/unit/test_agent_selection.py -v`

### 14. UPDATE `src/agents/nodes/response_node.py:_build_context` — Dispatch on `user_intent`

- **IMPLEMENT**: Rewrite the function body at lines 153-206 to switch on `user_intent` for the flow, with legacy fallback:
  ```python
  def _build_context(state: AgentState) -> str:
      """Build a selective JSON context string based on user_intent + pipeline_stage."""
      from src.agents.state import intent_from_legacy, stage_from_legacy

      intent = state.get("user_intent") or intent_from_legacy(state.get("last_action")) or ""
      stage = state.get("pipeline_stage") or stage_from_legacy(state.get("last_action")) or ""

      # Keep last_action in the context for one release — the LLM prompt
      # still references it. Remove when last_action is removed.
      context: dict = {
          "user_intent": intent,
          "pipeline_stage": stage,
          "last_action": state.get("last_action", ""),
      }

      if intent == "LOG_FOOD" or intent == "LOG_PERSONAL_STATS":
          # Food-logging or stats-logging flow — include per-item processing results
          # and the consumed_at the user gave (for "logged at..." phrasing).
          log_food = state.get("log_food", {})
          consumed_at = log_food.get("consumed_at")
          if consumed_at:
              context["consumed_at"] = (
                  consumed_at.isoformat()
                  if isinstance(consumed_at, datetime)
                  else str(consumed_at)
              )
          context["processing_results"] = state.get("processing_results", [])

      elif intent == "QUERY_DAILY_STATS":
          # Stats query flow — include raw daily log report + date hints.
          context["query_logs"] = state.get("query_logs", [])
          query_stats = state.get("query_stats", {})
          for key in ("target_date", "start_date", "end_date"):
              val = query_stats.get(key)
              if val is not None:
                  context[key] = val.isoformat() if isinstance(val, date) else str(val)

      # For CHITCHAT, QUERY_FOOD_INFO, or unknown intent: minimal context.

      return json.dumps(context, indent=2, default=_serialize_date)
  ```
- **PATTERN**: Existing `_build_context` already does selective context construction; we're just switching the discriminator from `last_action` (mixed) to `user_intent` (pure).
- **GOTCHA**: The previous condition at line 162 included `LOG_FOOD` AND five pipeline-stage values. The new condition is just `LOG_FOOD`. This still works because: when the LOG path runs, `user_intent` stays `LOG_FOOD` throughout, even as pipeline_stage moves through SELECTED → AWAITING_CONFIRMATION → CONFIRMED → LOGGED. The legacy fallback ensures pre-refactor checkpoints (where only `last_action` exists, possibly set to `CONFIRMED`/`LOGGED`/etc.) still resolve to `LOG_FOOD` via the new mapping — **BUT**: `_intent_from_legacy("CONFIRMED")` returns `None` because `CONFIRMED` is in stage values, not intent values. **Edge case to verify**: a pre-refactor checkpoint where `last_action == "LOGGED"` won't resolve to `LOG_FOOD` via fallback. Mitigation: response_node also checks `processing_results` length / `query_logs` length as a structural hint. **Decision needed during implementation**: either (a) accept that pre-refactor checkpoints get "minimal context" rendering during the deprecation window (acceptable — affects only ~30 min of paused threads at deploy time), or (b) extend the fallback to derive intent from substate presence (`log_food` populated → LOG_FOOD intent). Recommend (a) for simplicity.
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v`

### 15. UPDATE `prompts/response_generator.md` — Reference `user_intent`

- **IMPLEMENT**: At line 27, change `last_action` is `QUERY_DAILY_STATS` to `user_intent` is `QUERY_DAILY_STATS`. Search the file for any other occurrences (`grep -n "last_action" prompts/response_generator.md`) and update.
- **PATTERN**: Prompt is plain markdown; field names are referenced verbatim.
- **GOTCHA**: The prompt also reads from the JSON context block we emit. Since we kept `last_action` in the JSON context for one release (Task 14), the prompt could reference either field. Switch the prompt to `user_intent` — it's the authoritative field.
- **VALIDATE**: `grep -n "last_action" prompts/response_generator.md` should return zero lines.

### 16. UPDATE `tests/unit/test_state_consistency.py` — Add new Literal integrity tests

- **IMPLEMENT**: Add a second test class `TestUserIntentIntegrity` and `TestPipelineStageIntegrity` mirroring the existing pattern. Each asserts:
  - `UserIntent` values exactly match `ActionType` enum.
  - `PipelineStage` values include `SELECTED`, `NO_MATCH`, `AMBIGUOUS` (from `SelectionStatus`), plus `PENDING`, `AWAITING_CONFIRMATION`, `CONFIRMED`, `REJECTED`, `LOGGED`.
  - `UserIntent` and `PipelineStage` are disjoint (no value appears in both).
- **PATTERN**: Mirror the existing `TestGraphActionIntegrity` at line 17.
- **VALIDATE**: `uv run pytest tests/unit/test_state_consistency.py -v`

### 17. UPDATE writer tests — Add parallel assertions on new fields

- **IMPLEMENT**: For each of the following files, locate the existing `assert result["last_action"] == "..."` lines and add a parallel assertion immediately after:
  - `tests/unit/test_input_parser.py` (lines 69, 128, 156, 175, 193, 212): add `assert result["user_intent"] == "<same-value>"` and `assert result["pipeline_stage"] == "PENDING"`.
  - `tests/unit/test_agent_selection.py` (lines 34, 50, 93, 118): add `assert result["pipeline_stage"] == "<same-value>"`.
  - `tests/unit/test_calculate_macros_node.py` (lines 114, 138): add `assert result["pipeline_stage"] == "<same-value>"`.
  - `tests/unit/test_confirmation_node.py` (lines 253, 275): add `assert result.update["pipeline_stage"] == "<same-value>"`.
  - `tests/unit/test_commit_node.py` (line 94): add `assert result["pipeline_stage"] == "LOGGED"`.
  - `tests/unit/test_personal_stats_node.py` (lines 53, 91): add `assert result["pipeline_stage"] == "LOGGED"`.
  - `tests/unit/test_multi_item_loop.py` (lines 59, 79): add `assert result["pipeline_stage"] == "AWAITING_CONFIRMATION"`.
  - `tests/unit/test_feedback_logic.py` (lines 137, 168): add `assert result["pipeline_stage"] == "NO_MATCH"`.
- **PATTERN**: Tests follow the AAA structure; assertions live in the assert section of the test.
- **GOTCHA**: Don't remove the existing `last_action` assertions — they verify dual-write integrity.
- **VALIDATE**: `uv run pytest tests/unit/ -v`

### 18. UPDATE state-setup tests — Populate new fields

- **IMPLEMENT**: For test files that build states manually (not via `basic_state` fixture):
  - `tests/unit/test_feedback_integration.py` (lines 52, 64, 81, 100, 118): every state dict with `"last_action": "<value>"` — add the parallel field. If `<value>` is intent-like, add `"user_intent": "<value>"`. If stage-like, add `"pipeline_stage": "<value>"`. Reference the disjoint sets from Task 16.
  - `tests/unit/test_calculate_macros_node.py:325`: same.
  - `tests/unit/test_multi_item_loop.py:150` (`basic_state["last_action"] = "LOG_FOOD"`): add `basic_state["user_intent"] = "LOG_FOOD"`.
  - `tests/integration/test_log_yesterday_e2e.py:78` (`"last_action": "CONFIRMED"`): add `"pipeline_stage": "CONFIRMED"`.
- **PATTERN**: Same dual-write pattern as nodes, applied to test state builders.
- **VALIDATE**: `uv run pytest tests/unit/ tests/integration/ -v` (integration requires Supabase DB).

### 19. UPDATE `tests/unit/test_response_node.py` — Extend `_make_state` helper

- **IMPLEMENT**: At lines 20-34, extend the `_make_state` helper:
  ```python
  def _make_state(**overrides):
      """Build a minimal AgentState dict with sensible defaults."""
      legacy_action = overrides.get("last_action", "LOGGED")
      # Auto-derive user_intent and pipeline_stage from last_action if not explicit.
      from src.agents.state import intent_from_legacy, stage_from_legacy
      default_intent = intent_from_legacy(legacy_action) or ""
      default_stage = stage_from_legacy(legacy_action) or ""

      state = {
          "messages": [HumanMessage(content="I ate 200g chicken")],
          "pending_food_items": [],
          "log_food": {"consumed_at": datetime(2026, 2, 20, 12, 0)},
          "query_stats": {},
          "last_action": legacy_action,
          "user_intent": overrides.get("user_intent", default_intent),
          "pipeline_stage": overrides.get("pipeline_stage", default_stage),
          "search_results": [],
          "selected_food_id": None,
          "processing_results": [],
          "daily_log_today": [],
      }
      state.update(overrides)
      return state
  ```
- **PATTERN**: Defaults derived from the existing `last_action` keep the 27 existing tests passing without per-test edits.
- **GOTCHA**: A test that passes `last_action="LOGGED"` (a stage) gets `user_intent=""`. The new `_build_context` returns minimal context for empty intent. Verify each existing test still passes. If any fail, the test was relying on `last_action` having the intent meaning even though it was passing a stage value — that test needs to explicitly pass `user_intent="LOG_FOOD"`.
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v`

### 20. CREATE `tests/unit/test_intent_stage_invariants.py` — Refactor-specific invariants

- **IMPLEMENT**: New test file. Three test classes:
  - `TestUserIntentImmutability` — invokes a sequence of nodes (mocked LLM/tool) starting from `input_parser_node` through `selection_node` and `calculate_macros_node`. Asserts `user_intent` value is identical at every stage.
  - `TestPipelineStageTransitions` — asserts each writer node sets the expected `pipeline_stage` value: input→PENDING, selection→SELECTED or NO_MATCH, calculate_macros→AWAITING_CONFIRMATION or NO_MATCH, confirmation→CONFIRMED or REJECTED, commit→LOGGED, personal_stats→LOGGED.
  - `TestLegacyCheckpointFallback` — invokes `route_parser` and `route_after_selection` with state dicts that have only `last_action` set (no `user_intent`/`pipeline_stage`). Asserts both routers return correct destinations via the fallback helpers.
- **PATTERN**: Mirror `tests/unit/test_state_substates.py` — same class-grouped style, AAA docstrings, mocked LLM via `_mock_input_llm` style helper.
- **GOTCHA**: These tests are the regression coverage that protects the refactor's invariants. Make them explicit and well-named so future contributors understand the contract.
- **VALIDATE**: `uv run pytest tests/unit/test_intent_stage_invariants.py -v`

### 21. UPDATE `src/agents/nutritionist.py:route_after_calculate_macros` — Gate QUERY_FOOD_INFO

- **IMPLEMENT**: Change the router at lines 39-43 to:
  ```python
  def route_after_calculate_macros(state: AgentState):
      """Loop back if more items pending; QUERY_FOOD_INFO skips confirmation/commit."""
      from src.agents.state import intent_from_legacy
      if state.get("pending_food_items", []):
          return "food_search"  # Process next item
      intent = state.get("user_intent") or intent_from_legacy(state.get("last_action"))
      if intent == "QUERY_FOOD_INFO":
          return "load_daily_context"  # Skip confirmation + commit — answer the question
      return "confirmation"  # LOG_FOOD path
  ```
- **PATTERN**: Same conditional-edge style as `route_parser` and `route_after_selection`.
- **GOTCHA**: The multi-item loop check (`pending_food_items`) must stay FIRST — a multi-item QUERY_FOOD_INFO turn still needs to process all items before answering.
- **VALIDATE**: `uv run pytest tests/unit/test_multi_item_loop.py tests/unit/test_calculate_macros_node.py -v`

### 22. UPDATE `src/agents/nutritionist.py` graph builder — Add `load_daily_context` to edges map

- **IMPLEMENT**: At lines 80-87 (the `add_conditional_edges` call for `calculate_macros`), add `"load_daily_context"` to the destinations dict:
  ```python
  workflow.add_conditional_edges(
      "calculate_macros",
      route_after_calculate_macros,
      {
          "food_search": "food_search",
          "confirmation": "confirmation",
          "load_daily_context": "load_daily_context",  # NEW — QUERY_FOOD_INFO path
      },
  )
  ```
- **PATTERN**: LangGraph conditional-edges map — every router return value needs a destination entry.
- **GOTCHA**: If you forget this, LangGraph raises at graph-compile time. Caught by `test_graph_compilation.py`.
- **VALIDATE**: `uv run pytest tests/graph_api/test_graph_compilation.py -v`

### 23. UPDATE `src/agents/nodes/response_node.py:_build_context` — Add QUERY_FOOD_INFO branch

- **IMPLEMENT**: Extend the `_build_context` function (which Task 14 already migrated to dispatch on `user_intent`) with a new branch for `QUERY_FOOD_INFO`. Add between the `LOG_FOOD` branch and the `QUERY_DAILY_STATS` branch:
  ```python
  elif intent == "QUERY_FOOD_INFO":
      # Nutrition Q&A — the LOG pipeline ran to retrieve DB macros, but the
      # user asked a question, not a log. Surface the looked-up macros so
      # the LLM answers with DB-grounded numbers.
      queried = state.get("pending_confirmations", [])
      context["queried_foods"] = [
          {
              "name_en": item.get("name_en"),
              "name_he": item.get("name_he"),
              "amount_g": item.get("amount_g"),
              "calories": item.get("calories"),
              "protein": item.get("protein"),
              "carbs": item.get("carbs"),
              "fat": item.get("fat"),
              "source": item.get("source"),  # "database" or "estimated"
          }
          for item in queried
      ]
  ```
- **PATTERN**: Mirrors the existing `QUERY_DAILY_STATS` branch (surfaces `query_logs` from state for the LLM).
- **GOTCHA**: `pending_confirmations` is not cleared on the QUERY path (no `commit_node` runs to reset it). That's fine — the field is reset at turn start by `input_parser_node` (input_node.py line ~100 already does this).
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v`

### 24. UPDATE `prompts/response_generator.md` — Handle `queried_foods` for nutrition Q&A

- **IMPLEMENT**: Add a new section to the prompt (alongside the existing `QUERY_DAILY_STATS` branch instruction at line 27) covering the QUERY_FOOD_INFO case. Suggested copy:
  ```markdown
  - `user_intent` is `QUERY_FOOD_INFO` and `queried_foods` is present in the context → **Nutrition Q&A template**:
    - Answer the user's question using the macro values in `queried_foods` (these are DB-looked-up or LLM-estimated values for the food the user asked about).
    - DO NOT use logging language ("I logged", "I'll add this", "do you want me to log this?"). The user asked a question; they did not ask to log.
    - If `source` is `"estimated"`, hedge ("approximately", "around") and note it's an estimate, not a catalog value.
    - Match the user's language (en or he).
  ```
- **PATTERN**: The existing prompt has per-action rendering rules — extend that section.
- **GOTCHA**: Verify the prompt's overall structure isn't broken. The prompt already references `last_action` (Task 15 changed it to `user_intent`); confirm Task 15 + Task 24 don't conflict by re-reading the file.
- **VALIDATE**: `grep -n "queried_foods\|user_intent" prompts/response_generator.md` — both tokens should appear.

### 25. ADD E2E test for QUERY_FOOD_INFO routing — `tests/graph_api/test_graph_flows.py`

- **IMPLEMENT**: Append a new test class to `test_graph_flows.py`. **Mandatory DB-level assertion**: snapshot `daily_logs` count for the test user before and after the run, assert it is unchanged. This is the regression test that actually proves the silent-commit bug is fixed — string-level response checks alone are not enough (the previous "cancellation-by-three-bugs" produced the same surface response while still being one bug-fix away from disaster).
  ```python
  class TestQueryFoodInfoPath:
      """QUERY_FOOD_INFO routes through food_search + calculate_macros for DB macros,
      then skips confirmation + commit and answers the question — no row written."""

      async def test_query_food_info_does_not_commit(self, lg_client, thread, async_test_db_session):
          """
          arrange: User asks a nutrition question about a known food.
          act:     Graph routes through food_search → agent_selection → calculate_macros,
                   then skips confirmation/commit and goes to response.
          assert:  (1) No HITL interrupt fires (the user asked a question, not a log).
                   (2) daily_logs row count for the test user is unchanged across the run.
                   (3) Final message is non-empty and references the queried food's macros.
          """
          from sqlalchemy import select, func
          from src.models import DailyLog

          tn = "test_query_food_info_does_not_commit"
          user_id = DEV_USER_CONTEXT["user_id"]

          # Snapshot daily_logs count BEFORE the run.
          before_count = (
              await async_test_db_session.execute(
                  select(func.count()).select_from(DailyLog).where(DailyLog.user_id == user_id)
              )
          ).scalar_one()

          result = await _run(
              lg_client, thread,
              input={"messages": [{"role": "human", "content": "How much protein is in 100g of chicken?"}]},
              context=DEV_USER_CONTEXT,
              test_name=tn,
          )

          # Assertion 1: no HITL interrupt.
          state = await lg_client.threads.get_state(thread)
          assert not state.get("tasks"), (
              f"Expected no HITL interrupt for QUERY_FOOD_INFO, but graph paused.\n"
              f"Tasks: {state.get('tasks')}"
          )

          # Assertion 2: zero new daily_logs rows.
          after_count = (
              await async_test_db_session.execute(
                  select(func.count()).select_from(DailyLog).where(DailyLog.user_id == user_id)
              )
          ).scalar_one()
          assert after_count == before_count, (
              f"QUERY_FOOD_INFO silently committed a daily_log row.\n"
              f"Before: {before_count}, After: {after_count}.\n"
              f"This is the bug this PR exists to fix — the routing gate is not working."
          )

          # Assertion 3: response shape.
          messages = result.get("messages", [])
          assert len(messages) >= 2
          assert messages[-1]["content"].strip() != ""
          response_text = messages[-1]["content"].lower()
          assert "protein" in response_text or any(c.isdigit() for c in response_text)
  ```
- **PATTERN**: Mirror `TestQueryStatsPath` in the same file (lines 196-214); the DB-snapshot pattern mirrors `tests/integration/test_log_yesterday_e2e.py` where DB state is also asserted post-run.
- **GOTCHA**:
  - Pulls `DailyLog` from `src/models.py` and uses the integration-style `async_test_db_session` fixture from `tests/conftest.py`. Confirm the graph-api tests have access to that fixture; if not, build a small async engine inline (mirror conftest:69-77) or fold the DB read into a separate helper that the test composes.
  - `async_test_db_session` runs in a rolled-back transaction. Verify the LangGraph server (separate process) sees the committed state — the bot's writes go to the real Supabase DB, NOT the test session. Adjust: use a plain async session against the real DB for the snapshot reads (no rollback wrapper), since we are checking what the server-side commit_node would have written.
  - Use a food guaranteed to exist in the DB (chicken is seeded; "Test Chicken" id `11111111-...` is the conftest seed but it's transactional). For the real-server path, query something the server's DB has — `chicken` is fine, the production seed includes it.
- **VALIDATE**: `uv run pytest tests/graph_api/test_graph_flows.py::TestQueryFoodInfoPath -v -s`

### 26. UPDATE `notebooks/evals/eval_input_parser_hebrew.py` and `eval_input_parser.ipynb`

- **IMPLEMENT**:
  - `eval_input_parser_hebrew.py:454` — change `"action": result["last_action"]` to `"action": result["user_intent"]`.
  - `eval_input_parser.ipynb` cell at line 273 — same change inside the JSON-string source.
- **PATTERN**: Eval framework reads a single field as the parser's output label.
- **GOTCHA**: Eval datasets (uploaded to LangSmith) reference the dataset's input columns, not the field name in the parser's output. No dataset re-upload needed.
- **VALIDATE**: `uv run python notebooks/evals/eval_input_parser_hebrew.py --dry-run` (or whatever the script's dry-run flag is; if none, run a single example).

### 27. UPDATE `docs/patterns/state-schemas.md` — Document the split

- **IMPLEMENT**:
  - Update the AgentState field table (lines 45-56) to include rows for `user_intent` and `pipeline_stage`, and mark `last_action` as "deprecated; removal tracked in TASKS.md".
  - At line 99 (the GraphAction bullet), add a paragraph: "Intent and stage are split since ADR-0005. `user_intent` is set once by the parser and immutable for the turn. `pipeline_stage` is overwritten freely by intermediate nodes. `last_action` remains for one release as a deprecated alias to protect pre-refactor checkpoints."
- **PATTERN**: Existing table style.
- **VALIDATE**: `grep "user_intent\|pipeline_stage" docs/patterns/state-schemas.md` returns hits.

### 28. CREATE `docs/adr/0005-split-user-intent-from-pipeline-stage.md`

- **IMPLEMENT**: Use the `/adr` skill or write directly. Required sections (mirror ADR-0004 style):
  - **Status**: Accepted YYYY-MM-DD
  - **Area**: state, routing
  - **Deciders**: Dolev (with Claude Opus 4.7)
  - **Context**: `last_action` doing two jobs; symptoms (QUERY_FOOD_INFO bug, response_node over-generalization, NO_MATCH overload).
  - **Decision**: Split into `user_intent` (immutable per turn) and `pipeline_stage` (mutable). Keep `last_action` for one release.
  - **Alternatives considered**:
    - (A) Keep `last_action` monolithic, add a shadow `original_action` field — rejected because still ambiguous; doesn't fix `_build_context`.
    - (B) Use substate-presence as discriminator (e.g., `log_food` populated → LOG_FOOD intent) — rejected because makes intent a derived property, fragile to future substate additions.
    - (C) Hard-cut migration (no `last_action` for one release) — rejected because of paused HITL checkpoints.
  - **Consequences**: What's easier (clean QUERY_FOOD_INFO fix, less over-generalized response logic); what's harder (two fields to keep consistent during deprecation; one extra field for each node return); what we're committing to (the substate naming triad extends naturally; future "originating intent" needs all use `user_intent`).
  - **Revisit trigger**: If pipeline_stage values exceed ~10 distinct states or get reused across intents, consider per-intent state machines.
  - **Related**: ADR-0004, the substate pattern this extends; this plan; the QUERY_FOOD_INFO planning doc.
- **PATTERN**: ADR-0004 (`docs/adr/0004-schema-to-state-translation-ownership.md`) is the closest template.
- **VALIDATE**: File exists, has all required sections. Append a line to `docs/adr/DECISIONS.md`.

### 29. UPDATE `brain/TASKS.md` — Add follow-up tasks; close Important #2

- **IMPLEMENT**:
  - **Mark Important #2 (QUERY_FOOD_INFO Silent-Commit Risk) as completed** with reference to this PR. The fix shipped in this PR — bullet should move to the completed (✅) section with date and PR number.
  - Add two new tasks to the Maintenance section:
    1. **Remove `last_action` from `AgentState`** — after one release window (~2 weeks). Steps: drop field from state.py, remove dual-write in 6 writer nodes, remove `intent_from_legacy`/`stage_from_legacy` helpers, remove backwards-compat reads in routers and `_build_context`, remove `last_action` line from `_build_context`'s JSON context block, drop `GraphAction` Literal, drop the `last_action` references in tests.
    2. **NO_MATCH overload disambiguation** — split `pipeline_stage="NO_MATCH"` into `SELECTION_NO_MATCH` (selection_node) vs `MACRO_CALCULATION_FAILED` (calculate_macros_node). Currently same string, different cause.
- **PATTERN**: Existing Maintenance section style — numbered, terse, with source links.
- **VALIDATE**: Inspect TASKS.md visually.
- **PATTERN**: Existing Maintenance section style — numbered, terse, with source links.
- **VALIDATE**: Inspect TASKS.md visually.

### 30. VALIDATE end-to-end — Full suite

- **IMPLEMENT**: Run the full validation pyramid. Address any regressions before declaring done.
- **VALIDATE**:
  - `uv run ruff check .`
  - `uv run pytest tests/unit/ -v`
  - `uv run pytest tests/integration/ -v` (requires Supabase DB)
  - `uv run pytest tests/graph_api/ -v -s` (E2E, slow — run last)

---

## TESTING STRATEGY

### Unit Tests

Per project convention (`.claude/skills/test-engineering/SKILL.md`): unit tests are fast, mock LLM + DB at the boundary, located in `tests/unit/`. Coverage targets:

- **Dual-write integrity**: every writer node test verifies both `last_action` and the new field carry the expected value.
- **User intent immutability** (new): a multi-node sequence preserves `user_intent`.
- **Pipeline stage transitions** (new): each writer sets the expected stage value at its boundary.
- **Legacy fallback** (new): routers and `_build_context` handle pre-refactor state dicts (only `last_action` populated).
- **Literal integrity** (extend `test_state_consistency.py`): `UserIntent` matches `ActionType`; `PipelineStage` matches `SelectionStatus` + extras; the two sets are disjoint.

### Integration Tests

`tests/integration/test_log_yesterday_e2e.py` already covers a HITL confirm path; updating its state-setup to include `pipeline_stage="CONFIRMED"` is the only change. No new integration tests required — the refactor is behavior-neutral.

### Graph-API (E2E) Tests

`tests/graph_api/test_graph_flows.py` covers all five routing paths (chitchat, personal stats, query stats, food logging confirm/reject/edit, multi-item, no-match-estimation). These tests don't assert on `last_action` directly — they assert on response shape. After the refactor:

- All existing E2E tests should pass unchanged (the refactor is behavior-neutral by design).
- E2E run is the definitive proof the routers work correctly with the new fields against the live LangGraph server.

### Edge Cases

- **Pre-refactor checkpoint resume**: a thread paused at HITL `interrupt()` whose checkpoint was written before the deploy. On resume, only `last_action` exists. Routers and `_build_context` use the legacy fallback. Covered by `TestLegacyCheckpointFallback` in Task 20.
- **Empty-string state**: tests/conftest.py `basic_state` ships `last_action=""`. After Task 3, also `user_intent=""` and `pipeline_stage=""`. `_build_context` already handles empty `last_action` (minimal context); the new logic also handles empty intent (same — minimal context).
- **Pydantic `UserIntent` → `UserIntentEvent` rename** must land first (Task 1) before the Literal of the same name is introduced. Order matters: do the rename, run parser tests, then add the Literal.
- **Naming collision in `response_node._build_context`**: the local variable `last_action` at line 159 has the same name as the state key. The new code reads `intent` and `stage` as separate variables; preserve the local-name vs state-key distinction.

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
```

Expected: zero failures, zero new skips.

### Level 3: Integration Tests

```bash
uv run pytest tests/integration/ -v
```

Requires `SUPABASE_DB_URL` env var (see `.env`). Expected: zero failures.

### Level 4: Graph-API E2E

```bash
uv run pytest tests/graph_api/ -v -s
```

Slow (auto-starts langgraph dev server, real LLM calls). Run after Levels 1–3 pass. Expected: zero failures.

### Level 5: Manual Validation

1. Start langgraph dev: `uv run langgraph dev`.
2. In LangSmith Studio, run each path:
   - "Hi" → CHITCHAT (no food/stats lookup).
   - "I weigh 74kg" → personal stats.
   - "What did I eat today?" → stats query.
   - "I ate 200g chicken" → food logging; confirm `yes` at HITL.
   - "I ate 200g chicken" → food logging; reject at HITL.
3. For each, inspect the final thread state in Studio:
   - `user_intent` field present and matches the parser's classification.
   - `pipeline_stage` field present and matches the last node that ran.
   - `last_action` field still present (dual-write working).
4. Inspect logs (`langgraph dev` console): node-level structured logs should still show `action=...` from input_parser; no errors.

---

## ACCEPTANCE CRITERIA

- [ ] Pydantic `UserIntent` renamed to `UserIntentEvent` in `src/schemas/input_schema.py` and all reference sites updated.
- [ ] `src/agents/state.py` defines `UserIntent` and `PipelineStage` Literals.
- [ ] `AgentState` TypedDict has `user_intent` and `pipeline_stage` fields.
- [ ] `last_action` is still present in `AgentState` and still written by every writer node (dual-write).
- [ ] `intent_from_legacy` and `stage_from_legacy` helpers exist and are used by routers and `_build_context`.
- [ ] All 6 writer nodes (`input_node`, `selection_node`, `calculate_macros_node`, `confirmation_node`, `commit_node`, `personal_stats_node`) write both the old field and the appropriate new field.
- [ ] `input_parser_node` is the sole writer of `user_intent`.
- [ ] `route_parser` reads `user_intent` (with legacy fallback).
- [ ] `route_after_selection` reads `pipeline_stage` (with legacy fallback).
- [ ] `route_after_calculate_macros` gates `QUERY_FOOD_INFO` to `load_daily_context` (skip confirmation + commit).
- [ ] `response_node._build_context` dispatches on `user_intent` for flow grouping; surfaces `queried_foods` for `QUERY_FOOD_INFO` intent.
- [ ] `prompts/response_generator.md` references `user_intent` instead of `last_action` and has a `QUERY_FOOD_INFO` answering section using `queried_foods`.
- [ ] New E2E test `TestQueryFoodInfoPath` proves no HITL interrupt and no DB write for a nutrition Q&A turn.
- [ ] All existing tests pass without removing any existing `last_action` assertions.
- [ ] New tests in `test_intent_stage_invariants.py` cover immutability, transitions, and legacy fallback.
- [ ] `test_state_consistency.py` has parallel integrity tests for `UserIntent` and `PipelineStage`.
- [ ] `notebooks/evals/eval_input_parser*.{py,ipynb}` read `user_intent`.
- [ ] `docs/patterns/state-schemas.md` documents the split.
- [ ] `docs/adr/0005-split-user-intent-from-pipeline-stage.md` exists.
- [ ] `brain/TASKS.md` has Important #2 marked complete and two new Maintenance follow-up tasks (last_action removal, NO_MATCH disambiguation).
- [ ] All validation levels (ruff, unit, integration, E2E) pass.
- [ ] No regressions in `langgraph dev` Studio manual validation, including the new QUERY_FOOD_INFO path (ask "how much protein in an egg?" — verify response answers the question and no log was written).

---

## COMPLETION CHECKLIST

- [ ] Open Questions resolved before coding (naming, HITL resume).
- [ ] All 30 tasks completed in order.
- [ ] Each task's `VALIDATE` command run and green.
- [ ] All validation levels (1–5) executed successfully.
- [ ] Full test suite passes (unit + integration + graph-api).
- [ ] No linting or type checking errors.
- [ ] Manual Studio validation confirms behavior unchanged.
- [ ] ADR-0005 written and linked from DECISIONS.md.
- [ ] TASKS.md updated with follow-up tasks.
- [ ] Commit log written per `.claude/skills/commit/SKILL.md`.
- [ ] PR description references this plan file.

---

## NOTES

### Open Questions

**1. Naming the new Literal type — DECIDED.**

The Pydantic `UserIntent` class is renamed to `UserIntentEvent` (matches the `Event` suffix convention from ADR-0004's naming triad). The new Literal takes the name `UserIntent`. Touchpoints for the rename: `src/schemas/input_schema.py:108` (class definition), `src/agents/nodes/input_node.py:14` (import), `src/agents/nodes/input_node.py:64` (the `with_structured_output(UserIntent)` call site). Other event variants (`LogFoodEvent`, `ChitchatEvent`, etc.) are imported by tests but the `UserIntent` wrapper class is not — no test changes needed for the rename itself.

**2. HITL resume semantics — does the parser overwrite `user_intent` on the user's "yes" reply?**

Today the parser runs on every turn, including HITL resume turns. A user replying "yes" to a confirmation prompt would have the parser classify "yes" — likely as `CHITCHAT`. With the dual-write in input_parser, this means `user_intent` flips from `LOG_FOOD` to `CHITCHAT` between Turn 1 (the food message) and Turn 2 (the "yes" reply).

Does this matter? Today the graph is paused at `interrupt()` inside `confirmation_node`, and on resume the graph **does not re-run** `input_parser_node` — it continues from the `interrupt()` point. So `user_intent` stays `LOG_FOOD` through HITL resume.

But: if a user sends a brand-new message (not a HITL resume — e.g., they cancel the modal and type a new query), then the parser runs fresh and `user_intent` updates. That's correct behavior.

**Decision**: no special handling needed. Document the invariant: `user_intent` is "the intent of the most recently parsed user message." Within a single HITL exchange, it persists; across new turns, it updates.

**3. Do we need a `query_food_info` substate at all?**

Substates carry action-specific extra data (`consumed_at`, `meal_type` for LOG_FOOD; `target_date`, `start_date`, `end_date` for QUERY_DAILY_STATS). QUERY_FOOD_INFO has no such extra data — the items the user asked about already live in `pending_food_items`. The `user_intent` field alone is sufficient to gate routing and rendering.

**Recommendation**: no substate. Skip it. `user_intent == "QUERY_FOOD_INFO"` is enough. If a future need surfaces (e.g., "answer in detailed-mode vs summary-mode"), add the substate then.

### Confidence Score

**Confidence: 7/10** for one-pass execution success.

Risks:
- **Test churn is large** (14 files + 1 new E2E test). High mechanical-error rate; mitigated by the `_make_state` helper update doing most of the load in `test_response_node.py` automatically.
- **`_build_context` edge case with pre-refactor `last_action="LOGGED"`** (Task 14 GOTCHA). If reviewers/tests catch a regression on paused-checkpoint resume, the fallback may need extension.
- **Naming decision** (Open Question #1) shapes the diff. Don't start until decided.
- **Bundled behavior change.** Refactor + bug fix in one PR means rollback rolls back both. The behavior change (`QUERY_FOOD_INFO` no longer routes through commit) needs Studio + E2E validation specifically; the refactor side won't catch regressions in the routing change.
- **Prompt edit dependence.** The QUERY_FOOD_INFO Q&A quality depends on `prompts/response_generator.md` doing the right thing with `queried_foods`. Prompt regressions are not always caught by tests — Studio validation is the safety net.

What pulls confidence up:
- The refactor side is behavior-neutral by design — every existing assertion can be left in place.
- Dual-write + legacy fallback is a well-known pattern; deprecation strategy is straightforward.
- The substate pattern this extends is already in the codebase (ADR-0004) — the cognitive load on reviewers is low.
- The QUERY_FOOD_INFO routing change is small (5 lines in `route_after_calculate_macros` + edges-map entry + `_build_context` branch + prompt section). Each step has its own VALIDATE command.

### Out of Scope (Explicit)

The following are tempting follow-ons that are **explicitly deferred**:

- Removing `last_action` from state.
- Splitting `NO_MATCH` into `SELECTION_NO_MATCH` and `MACRO_CALCULATION_FAILED`.
- Restructuring or renaming `LogFoodSubState` / `QueryStatsSubState`.
- Adding a `query_food_info` substate (not needed — see Open Question #3).
- Renaming `pending_confirmations` or `processing_results`.

All deferred items are tracked as separate tasks in `brain/TASKS.md` (Task 29).

### Ship Strategy

**One PR.** The refactor and the QUERY_FOOD_INFO fix ship together because:

- The user opted for a single PR after weighing the tradeoffs.
- Rollback is `git revert` — clean even with both changes bundled.
- The legacy-fallback design means pre-refactor checkpoints survive whether the QUERY_FOOD_INFO gate exists or not (the gate doesn't run on resume — it runs on fresh turns).

The `last_action` removal is a later cleanup PR after the deprecation window (~2 weeks post-deploy).

**Deploy plan:**

1. Land this PR on `main`. CI runs (lint + unit + integration). Manual `workflow_dispatch` triggers E2E.
2. CD pipeline builds Docker images and redeploys langgraph-server + fitpal-bot on Railway.
3. After deploy, do the manual Studio validation pass (Validation Level 5) including the new QUERY_FOOD_INFO path.
4. Monitor logs for 24 hours. Specifically watch for: `BlockingError` (none expected), unexpected `route_after_calculate_macros` returns to `load_daily_context` for non-QUERY turns (shouldn't happen), and any prompt-regression complaints (response_node answering nutrition questions in a logging-shaped voice).
