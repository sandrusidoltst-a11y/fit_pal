# Feature: Remove `last_action` deprecated field — fold into PR #32

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files.

## Feature Description

PR #32 (`refactor/split-user-intent-pipeline-stage`) split `AgentState.last_action` into `user_intent` + `pipeline_stage` and kept `last_action` as a **dual-written deprecated alias for one release** to protect paused HITL checkpoints. On review, that back-compat layer turned out to be a belt-and-suspenders that doesn't actually protect against any realistic scenario:

- The only graph node that pauses (`confirmation_node`) doesn't read `user_intent` or `pipeline_stage` on resume — it reads `pending_confirmations`, `log_food`, `processing_results`. Unchanged by the refactor.
- Routers (`route_parser`, `route_after_selection`) run only on **fresh** turns, where the parser always sets `user_intent` first. The legacy fallback never fires in practice.
- `_build_context` is the only reader that *could* benefit, but pre-refactor checkpoints have `last_action` set to a stage value (`AWAITING_CONFIRMATION`, `CONFIRMED`, etc.) which `intent_from_legacy` returns `None` for — the fallback is a no-op there.

The cost of keeping it is real: **dual review burden** (this PR and a follow-up cleanup PR ~2 weeks later), 30+ extra lines across the codebase, and a deprecation flag in every node return that invites confusion.

This plan removes `last_action`, `GraphAction`, `intent_from_legacy`, `stage_from_legacy`, and every reference to them — **as a follow-up commit on the same branch `refactor/split-user-intent-pipeline-stage`** before merging PR #32. The result is the clean post-deprecation state without the deprecation window.

## User Story

As a **FitPal reviewer**
I want to **review one PR with a clean state shape rather than two PRs that introduce-then-remove the same dead-weight field**
So that **I'm not asked to approve code that everyone already knows is going away**.

## Problem Statement

After PR #32 landed, every writer node dual-writes `last_action` alongside the new `user_intent` / `pipeline_stage` fields, every router falls back through `intent_from_legacy` / `stage_from_legacy`, and `_build_context` still emits `last_action` in its JSON context. The deprecated alias accomplishes nothing measurable — its only theoretical purpose (paused-HITL checkpoint resume) is moot because the resume path doesn't depend on the new fields, and pre-refactor checkpoints store stage values that don't map to intents anyway.

The follow-up "remove `last_action`" task is already in `brain/TASKS.md` Maintenance section. Executing it now folds the cleanup into the same review window.

## Solution Statement

Delete the deprecated field, type, helpers, and every reference. Six writer nodes drop one line from their return dict. Three router functions drop the `or *_from_legacy(...)` fallback chain. `_build_context` drops the `last_action` JSON-context entry, the fallback reads, and the docstring caveat. Tests update by either removing the now-obsolete `last_action` assertions or switching them to assert on the new fields directly. ADR-0005 + the review guide get edited to reflect the actual landed shape (no deprecation window).

The whole change is mechanical — no logic changes, no new behavior. **Behavior-neutral cleanup.**

## Feature Metadata

**Feature Type**: Refactor (cleanup)
**Estimated Complexity**: Low-Medium
**Primary Systems Affected**:
- `src/agents/state.py` (type + helper removal)
- 6 writer nodes (drop one line each)
- `src/agents/nutritionist.py` (3 router simplifications)
- `src/agents/nodes/response_node.py` (`_build_context` cleanup)
- 13 test files (assertion + state-setup cleanup)
- 3 doc files (ADR-0005, state-schemas.md, review guide)
- `brain/TASKS.md` (close out the maintenance follow-up since we're doing it now)

**Dependencies**: None — pure deletion + ripple updates. No new packages, no schema changes.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — YOU MUST READ THESE BEFORE IMPLEMENTING

#### State definitions

- `src/agents/state.py` (lines 60-73, 74-78, 107-130, 228-230, 246-247) — Why: Contains `GraphAction` Literal (60-73), its DEPRECATED comment block (74-78), the `_INTENT_VALUES` / `_STAGE_VALUES` sets (107-111), `intent_from_legacy` (114-123), `stage_from_legacy` (126-130), the field docstring (228-230), and the field declaration (247). All five blocks come out. `get_args` import on line 2 is no longer needed after removal — drop it.
- `src/agents/state.py` (line 148, 155) — Why: Docstrings for `LogFoodSubState` and `QueryStatsSubState` mention `last_action`. Update to reference `user_intent` instead.

#### Writer nodes

- `src/agents/nodes/input_node.py` (lines 92-105) — Why: Drop the `"last_action": result.action.value,` line and its DEPRECATED comment.
- `src/agents/nodes/selection_node.py` (lines 36-94) — Why: Five `"last_action": ...` lines at 38, 46, 83, 91, 97 — drop all.
- `src/agents/nodes/calculate_macros_node.py` (lines 71-77, 120-125) — Why: Two `"last_action": ...` lines at 75 and 124 — drop both.
- `src/agents/nodes/confirmation_node.py` (lines 147-154, 174-183) — Why: Two `"last_action": ...` lines inside `Command.update` dicts at 149 and 178 — drop both.
- `src/agents/nodes/commit_node.py` (lines 99-103) — Why: One `"last_action": "LOGGED",` line at 101 — drop.
- `src/agents/nodes/personal_stats_node.py` (lines 77-80) — Why: One `"last_action": "LOGGED",` line at 78 — drop.

#### Readers

- `src/agents/nutritionist.py` (lines 14-19, 22-52) — Why: Drop `intent_from_legacy`, `stage_from_legacy` imports. Simplify three routers — read `state.get("user_intent")` / `state.get("pipeline_stage")` directly without the `or *_from_legacy(...)` fallback.
- `src/agents/nodes/response_node.py` (lines 153-207) — Why: `_build_context` simplification. Drop fallback reads (lines 162-165), drop `last_action` field in emitted JSON context (line 171), update docstring (lines 154-160).

#### Tests

- `tests/conftest.py` (line 52) — Why: Drop `"last_action": ""` from `basic_state` fixture.
- `tests/unit/test_state_consistency.py` (lines 12, 17-41) — Why: Drop `GraphAction` import and the entire `TestGraphActionIntegrity` class (the new `UserIntent` / `PipelineStage` classes remain).
- `tests/unit/test_intent_stage_invariants.py` (lines 9-11, 24, 86-89, 126-160) — Why: Drop docstring mention of "legacy-fallback path", drop the `intent_from_legacy` / `stage_from_legacy` imports, drop the `assert result["last_action"] == "QUERY_FOOD_INFO"` line in `TestUserIntentImmutability::test_query_food_info_intent_survives_through_parser`, and drop the entire `TestLegacyCheckpointFallback` class.
- `tests/unit/test_response_node.py` (lines 17-55, 64-186, 449+) — Why: **The biggest test change.** `_make_state` helper currently auto-derives `user_intent` / `pipeline_stage` from a `last_action` overrideable arg. Replace with direct `user_intent` / `pipeline_stage` parameters; drop the `last_action` key from the returned state dict. Then walk every existing test that calls `_make_state(last_action="...")` and convert it to `_make_state(user_intent=..., pipeline_stage=...)` (or just `user_intent=...` since pipeline_stage isn't asserted on outside `test_intent_stage_invariants.py`). Drop assertions on `parsed["last_action"]` — most are duplicate of `parsed["user_intent"]` which already exists; for the ones that test the empty-context fall-through, switch to `parsed["user_intent"] == ""`.
- `tests/unit/test_input_parser.py` (lines 69, 130, 160, 181, 200, 221) — Why: Six `assert result["last_action"] == "..."` lines. The parallel `result["user_intent"] == "..."` and `result["pipeline_stage"] == "PENDING"` assertions already exist (added in PR #32 Task 17). Just drop the `last_action` lines.
- `tests/unit/test_agent_selection.py` (lines 34, 51, 95, 121) — Why: Four `assert result["last_action"] == "..."` lines. Parallel `pipeline_stage` assertions already exist. Drop the `last_action` lines.
- `tests/unit/test_calculate_macros_node.py` (lines 114, 139, 327) — Why: Two assertions + one state-setup `"last_action": "NO_MATCH"` line (327). Parallel `pipeline_stage` assertions exist. Drop both assertion lines and the state-setup line.
- `tests/unit/test_confirmation_node.py` (lines 253, 276) — Why: Two `Command.update["last_action"]` assertions. Parallel `pipeline_stage` assertions exist. Drop the `last_action` lines.
- `tests/unit/test_commit_node.py` (line 94) — Why: One assertion. Parallel `pipeline_stage` exists. Drop.
- `tests/unit/test_personal_stats_node.py` (lines 53, 92) — Why: Two assertions. Parallel `pipeline_stage` exists. Drop.
- `tests/unit/test_multi_item_loop.py` (lines 59, 80, 152) — Why: Two assertions + one state-setup `basic_state["last_action"] = "LOG_FOOD"` line (152). Parallel new-field setups exist. Drop all three.
- `tests/unit/test_feedback_logic.py` (lines 137, 169) — Why: Two assertions. Parallel `pipeline_stage` exists. Drop.
- `tests/unit/test_feedback_integration.py` (lines 52, 66, 84, 104, 123) — Why: Five state-dict entries with `"last_action": "..."`. Parallel new-field entries exist. Drop the `last_action` lines.
- `tests/integration/test_log_yesterday_e2e.py` (line 78) — Why: One state-dict entry. Parallel `user_intent` + `pipeline_stage` entries exist. Drop the `last_action` line.

#### Docs

- `docs/patterns/state-schemas.md` (lines 45-99) — Why: AgentState field table includes a `last_action` row marked DEPRECATED, plus a paragraph at line 99 about "Kept for one release". Remove both. The `UserIntent` + `PipelineStage` rows stay.
- `docs/adr/0005-split-user-intent-from-pipeline-stage.md` (full file) — Why: Update to reflect that `last_action` was removed in the same PR, not kept as a deprecated alias. Specifically:
  - **Decision section**: rewrite the paragraph about "kept for one release as a deprecated parallel field" to "removed in the same PR after review-time validation showed the legacy-fallback layer doesn't fire in practice".
  - **Alternatives considered §C (hard-cut migration)**: it WAS rejected initially, but the review process found the rejection rationale was wrong (the resume path doesn't depend on the new fields). Either rewrite §C as the accepted approach or add a new "Note" section acknowledging the reversal.
  - **Consequences → What this makes harder**: drop the "two fields to keep consistent during deprecation" line.
  - **Consequences → What we are committing to**: drop the "removal of `last_action` is a tracked task" line.
- `docs/adr/DECISIONS.md` (lines 110+) — Why: The ADR-0005 index entry's one-liner says "`last_action` is kept dual-written for one release as a deprecated alias". Edit to match the new reality.
- `docs/plans/split-user-intent-from-pipeline-stage-review-guide.md` (full file) — Why: References the legacy-fallback helpers and the dual-write throughout. Either update inline or add a "Update" callout at the top noting the removal that landed alongside it. Recommend an inline update so reviewers reading the guide see the actual shape they're reviewing.
- `commit_logs/2026-05-11_22-43-48_split-user-intent-from-pipeline-stage.md` (full file) — Why: References the dual-write strategy and the follow-up `last_action` removal task. Add a note at the top: "Update YYYY-MM-DD: last_action removal folded into this PR — see commit_logs/<NEW_COMMIT_LOG>." Then write a fresh commit log for this removal commit.

#### TASKS.md (brain repo — separate)

- `brain/TASKS.md` (Maintenance section, "Remove `last_action`" entry) — Why: That follow-up task no longer exists. Mark it ✅ with same date as the merge, referencing the PR.

### New Files to Create

- `commit_logs/YYYY-MM-DD_HH-MM-SS_remove-last-action-deprecation.md` — fresh commit log for this removal commit. Brief: explains the back-compat layer turned out to be unnecessary, lists what was removed, references the previous commit + this plan.
- (No new source files.)

### Relevant Documentation — READ BEFORE IMPLEMENTING

- ADR-0005 (`docs/adr/0005-split-user-intent-from-pipeline-stage.md`) — the decision record this commit edits.
- `commit_logs/2026-05-11_22-43-48_split-user-intent-from-pipeline-stage.md` — the original commit log explaining why the dual-write was added; useful context for what we're removing.

### Patterns to Follow

#### Direct state reads after this commit

```python
# Before (with fallback):
intent = state.get("user_intent") or intent_from_legacy(state.get("last_action"))

# After:
intent = state.get("user_intent")
```

#### Test helper after this commit

```python
def _make_state(**overrides):
    """Build a minimal AgentState dict with sensible defaults."""
    state = {
        "messages": [HumanMessage(content="I ate 200g chicken")],
        "pending_food_items": [],
        "log_food": {"consumed_at": datetime(2026, 2, 20, 12, 0)},
        "query_stats": {},
        "user_intent": "LOG_FOOD",
        "pipeline_stage": "LOGGED",
        "search_results": [],
        "selected_food_id": None,
        "processing_results": [],
        "daily_log_today": [],
    }
    state.update(overrides)
    return state
```

#### Logging pattern

Unchanged. No structlog calls reference `last_action` today; removal doesn't affect logs.

---

## IMPLEMENTATION PLAN

### Phase 1: Source code — drop the field, type, helpers, and dual-writes

**Tasks:**
- Drop `last_action` from every node return dict (6 nodes, 12 sites).
- Drop `GraphAction` Literal, the deprecation comment, `_INTENT_VALUES` / `_STAGE_VALUES` sets, `intent_from_legacy`, `stage_from_legacy`, and the `get_args` import from `state.py`.
- Drop the `last_action: GraphAction` field declaration from `AgentState`.
- Simplify routers in `nutritionist.py` to read new fields directly.
- Simplify `_build_context` — direct reads, drop `last_action` from JSON context, update docstring.

After Phase 1, the only references to `last_action` in `src/` should be **zero**. The only references to `GraphAction` should be **zero**.

### Phase 2: Tests — drop legacy assertions and state-setup entries

**Tasks:**
- Update `tests/conftest.py::basic_state` to drop the `last_action` key.
- Update `tests/unit/test_state_consistency.py` — drop `TestGraphActionIntegrity` class and `GraphAction` import.
- Update `tests/unit/test_intent_stage_invariants.py` — drop `TestLegacyCheckpointFallback` class, drop `intent_from_legacy` / `stage_from_legacy` imports, drop one `last_action` assertion in `TestUserIntentImmutability`.
- Update `tests/unit/test_response_node.py::_make_state` — rewrite without legacy auto-derive; walk all `_make_state(last_action=...)` callers and switch to direct new-field params; drop `parsed["last_action"]` assertions.
- Walk 8 writer test files, drop the `last_action` assertions (parallel new-field assertions already exist).
- Drop `last_action` state-setup entries in 3 test files (`test_feedback_integration.py`, `test_calculate_macros_node.py:327`, `test_multi_item_loop.py:152`, `test_log_yesterday_e2e.py:78`).

### Phase 3: Docs — reflect the removed deprecation

**Tasks:**
- Update `docs/patterns/state-schemas.md` to drop the `last_action` table row and the deprecation paragraph.
- Update `docs/adr/0005-split-user-intent-from-pipeline-stage.md` — rewrite the Decision paragraph, edit the "What this makes harder" + "What we are committing to" sections, add a note explaining the §C alternative (hard-cut migration) was effectively chosen on review-time reconsideration.
- Update `docs/adr/DECISIONS.md` index entry one-liner.
- Update `docs/plans/split-user-intent-from-pipeline-stage-review-guide.md` — either inline updates throughout (preferred) or a clear "Update" callout at the top.
- Update `commit_logs/2026-05-11_22-43-48_split-user-intent-from-pipeline-stage.md` with a top "Update" note pointing at the new commit log.
- Create `commit_logs/<TIMESTAMP>_remove-last-action-deprecation.md` for this commit.

### Phase 4: Validate

**Tasks:**
- `uv run ruff check .` — should pass with zero diagnostics.
- `uv run pytest tests/unit/ -v` — expect 197 → ~190 passing (we're deleting `TestGraphActionIntegrity` = 1 test, `TestLegacyCheckpointFallback` = 3 tests, and possibly trimming a few assertions; should not introduce failures).
- `uv run pytest tests/integration/ -v` — expect 56 still passing.
- `uv run pytest tests/graph_api/ -v -s` — expect 15 still passing (real LLM, ~2 min).
- `grep -rn 'last_action\|GraphAction\|intent_from_legacy\|stage_from_legacy' src/ tests/ docs/patterns/ docs/adr/ prompts/ notebooks/evals/ 2>/dev/null` — should return only the unavoidable references in the plan + commit log historical files (which are fine, they're historical records).

### Phase 5: brain/TASKS.md follow-up + commit

**Tasks:**
- In `brain/` repo, edit `TASKS.md` Maintenance section: mark the "Remove `last_action`" entry as ✅ with date and PR reference. Note: this is a separate repo with its own Obsidian-Git plugin sync.
- In `fit_pal` repo, commit all changes atomically with a `refactor:` tag, referencing the original commit hash + this plan.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### 1. REMOVE `last_action` from `src/agents/nodes/input_node.py`

- **IMPLEMENT**: At line 92-105 (the return dict), drop the line `"last_action": result.action.value,        # DEPRECATED — see ADR-0005`. Leave `user_intent` and `pipeline_stage` untouched.
- **PATTERN**: Mirror existing turn-reset convention — keep writing the other turn-local fields.
- **GOTCHA**: Don't change `result.action.value` flow elsewhere — only the dict key drops.
- **VALIDATE**: `uv run pytest tests/unit/test_input_parser.py -v` — expect 6 assertions on `result["last_action"]` to now fail. We'll fix those in Task 13.

### 2. REMOVE `last_action` from `src/agents/nodes/selection_node.py`

- **IMPLEMENT**: At lines 38, 46, 83, 91, 97, drop each `"last_action": ...` line. Five sites. Leave `pipeline_stage` lines untouched.
- **PATTERN**: All five returns now contain only `selected_food_id` + `pipeline_stage`.
- **VALIDATE**: `uv run pytest tests/unit/test_agent_selection.py -v` — expect 4 assertions to now fail.

### 3. REMOVE `last_action` from `src/agents/nodes/calculate_macros_node.py`

- **IMPLEMENT**: At lines 75 and 124, drop the `"last_action": "NO_MATCH",` and `"last_action": "AWAITING_CONFIRMATION",` lines.
- **VALIDATE**: `uv run pytest tests/unit/test_calculate_macros_node.py -v` — expect failures on the assertions we'll fix in Task 15.

### 4. REMOVE `last_action` from `src/agents/nodes/confirmation_node.py`

- **IMPLEMENT**: At lines 149 and 178 (inside `Command(update={...})` dicts), drop the `"last_action": "CONFIRMED",` and `"last_action": "REJECTED",` lines.
- **GOTCHA**: `Command.update` is a dict — same mechanical edit as a node return.
- **VALIDATE**: `uv run pytest tests/unit/test_confirmation_node.py -v` — expect 2 assertion failures.

### 5. REMOVE `last_action` from `src/agents/nodes/commit_node.py`

- **IMPLEMENT**: At line 101, drop the `"last_action": "LOGGED",` line.
- **VALIDATE**: `uv run pytest tests/unit/test_commit_node.py -v` — expect 1 assertion failure.

### 6. REMOVE `last_action` from `src/agents/nodes/personal_stats_node.py`

- **IMPLEMENT**: At line 78, drop the `"last_action": "LOGGED",` line.
- **VALIDATE**: `uv run pytest tests/unit/test_personal_stats_node.py -v` — expect 2 assertion failures.

### 7. SIMPLIFY routers in `src/agents/nutritionist.py`

- **IMPLEMENT**:
  - Drop `intent_from_legacy`, `stage_from_legacy` from the `src.agents.state` import (lines 17-18).
  - In `route_parser` (~line 29), change `intent = state.get("user_intent") or intent_from_legacy(state.get("last_action"))` → `intent = state.get("user_intent")`.
  - In `route_after_selection` (~line 40), change `stage = state.get("pipeline_stage") or stage_from_legacy(state.get("last_action"))` → `stage = state.get("pipeline_stage")`.
  - In `route_after_calculate_macros` (~line 49), change `intent = state.get("user_intent") or intent_from_legacy(state.get("last_action"))` → `intent = state.get("user_intent")`.
- **PATTERN**: Direct state reads, no defensive fallback. The parser is guaranteed to set `user_intent` on every turn (turn-entry reset pattern in `input_node.py`).
- **GOTCHA**: Check no other site in `nutritionist.py` references the dropped imports — if it does, the import error fails the smoke test in the next task.
- **VALIDATE**: `uv run python -c "import asyncio; from src.agents.nutritionist import define_graph; asyncio.run(define_graph()); print('graph compiles')"` — should print "graph compiles".

### 8. SIMPLIFY `_build_context` in `src/agents/nodes/response_node.py`

- **IMPLEMENT**: At lines 153-207:
  - Update docstring (lines 154-160) — drop the paragraph about `last_action` conflating intent with stage and the legacy fallback caveat. Keep the brief explanation that it dispatches on `user_intent`.
  - Drop the `from src.agents.state import intent_from_legacy, stage_from_legacy` line (162).
  - Change `intent = state.get("user_intent") or intent_from_legacy(state.get("last_action")) or ""` → `intent = state.get("user_intent", "")`.
  - Change `stage = state.get("pipeline_stage") or stage_from_legacy(state.get("last_action")) or ""` → `stage = state.get("pipeline_stage", "")`.
  - Drop the `last_action = state.get("last_action", "")` line.
  - Drop the `"last_action": last_action,  # DEPRECATED — see ADR-0005` entry from the `context` dict.
- **PATTERN**: Same dispatch logic, simpler reads, smaller JSON context block.
- **GOTCHA**: The response prompt (`prompts/response_generator.md`) was already updated in PR #32 to reference `user_intent`, so the LLM contract is consistent. No prompt edit needed in this task.
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v` — expect failures on `parsed["last_action"]` assertions, which we'll fix in Task 16.

### 9. REMOVE legacy types and helpers from `src/agents/state.py`

- **IMPLEMENT**:
  - Drop `from typing import ... get_args` (line 2). Replace with `from typing import Annotated, List, Literal, Optional, TypedDict` (without `get_args`).
  - Drop the `GraphAction = Literal[...]` block (lines 60-73) entirely.
  - Drop the comment block at lines 74-78 (the DEPRECATED note).
  - Drop the legacy fallback helper block (lines 107-130): the `_INTENT_VALUES` / `_STAGE_VALUES` sets, both `intent_from_legacy` / `stage_from_legacy` functions, and the comment header.
  - In the `LogFoodSubState` docstring (line 148), change "Per-action sub-state — meaningful when last_action is LOG_FOOD/CONFIRMED/LOGGED" → "Per-action sub-state — meaningful when user_intent is LOG_FOOD".
  - In the `QueryStatsSubState` docstring (line 155), change "meaningful when last_action is QUERY_DAILY_STATS" → "meaningful when user_intent is QUERY_DAILY_STATS".
  - In the `AgentState` docstring (lines 228-236), drop the `last_action: DEPRECATED — see ADR-0005...` paragraph. Keep the `user_intent` and `pipeline_stage` paragraphs as-is.
  - Drop the field declaration `last_action: GraphAction  # DEPRECATED — see ADR-0005` (line 247).
- **GOTCHA**:
  - The `get_args` import was added in PR #32 specifically for the helper functions. Now no consumer in `state.py`. If any other file imports `get_args` from `src.agents.state` (vs from `typing` directly), update them — `grep -rn 'from src.agents.state import.*get_args' src/ tests/` should return zero.
  - Confirm `tests/unit/test_state_consistency.py` imports `get_args` from `typing` directly (it does — line 10). No ripple.
- **VALIDATE**: `uv run python -c "from src.agents.state import AgentState, UserIntent, PipelineStage; print('ok')"` should print `ok`. `uv run python -c "from src.agents.state import GraphAction"` should error with ImportError.

### 10. VALIDATE Phase 1 — graph still compiles, source has no last_action

- **IMPLEMENT**: No code change. Verification step.
- **VALIDATE**:
  - `grep -rn 'last_action\|GraphAction\|intent_from_legacy\|stage_from_legacy' src/ 2>/dev/null | grep -v __pycache__` — expect **zero results**.
  - `uv run python -c "import asyncio; from src.agents.nutritionist import define_graph; asyncio.run(define_graph()); print('ok')"` — prints `ok`.

### 11. UPDATE `tests/conftest.py::basic_state` fixture

- **IMPLEMENT**: At line 52, drop `"last_action": "",` from the dict. Keep `"user_intent": ""` and `"pipeline_stage": ""`.
- **VALIDATE**: `uv run pytest tests/unit/ -v --co | head -10` — collection still works.

### 12. UPDATE `tests/unit/test_state_consistency.py` — drop GraphAction test

- **IMPLEMENT**:
  - Drop `GraphAction` from the import on line 12: `from src.agents.state import GraphAction, PipelineStage, UserIntent` → `from src.agents.state import PipelineStage, UserIntent`.
  - Drop the entire `TestGraphActionIntegrity` class (lines 17-41).
- **PATTERN**: `TestUserIntentIntegrity`, `TestPipelineStageIntegrity`, `TestIntentStageDisjoint` continue to provide Literal coverage.
- **VALIDATE**: `uv run pytest tests/unit/test_state_consistency.py -v` — expect 4 tests passing (was 5).

### 13. UPDATE `tests/unit/test_input_parser.py` — drop last_action assertions

- **IMPLEMENT**: At lines 69, 130, 160, 181, 200, 221, drop each `assert result["last_action"] == "..."` line. Parallel `result["user_intent"] == "..."` and `result["pipeline_stage"] == "PENDING"` assertions already exist.
- **VALIDATE**: `uv run pytest tests/unit/test_input_parser.py -v` — expect 8 passing.

### 14. UPDATE `tests/unit/test_agent_selection.py` — drop last_action assertions

- **IMPLEMENT**: At lines 34, 51, 95, 121, drop each `assert result["last_action"] == "..."` line. Parallel `pipeline_stage` assertions already exist.
- **VALIDATE**: `uv run pytest tests/unit/test_agent_selection.py -v` — expect all passing.

### 15. UPDATE `tests/unit/test_calculate_macros_node.py` — drop last_action

- **IMPLEMENT**: Drop assertions at lines 114 and 139. Drop the state-setup line `"last_action": "NO_MATCH",` at line 327 (the parallel `"user_intent": "LOG_FOOD"` + `"pipeline_stage": "NO_MATCH"` entries already exist).
- **VALIDATE**: `uv run pytest tests/unit/test_calculate_macros_node.py -v`.

### 16. UPDATE `tests/unit/test_response_node.py` — rewrite `_make_state`, migrate 27 assertions

- **IMPLEMENT**:
  - Rewrite `_make_state(**overrides)` at lines 20-55:
    ```python
    def _make_state(**overrides):
        """Build a minimal AgentState dict with sensible defaults."""
        state = {
            "messages": [HumanMessage(content="I ate 200g chicken")],
            "pending_food_items": [],
            "log_food": {"consumed_at": datetime(2026, 2, 20, 12, 0)},
            "query_stats": {},
            "user_intent": "LOG_FOOD",
            "pipeline_stage": "LOGGED",
            "search_results": [],
            "selected_food_id": None,
            "processing_results": [],
            "daily_log_today": [],
        }
        state.update(overrides)
        return state
    ```
  - Walk every `_make_state(last_action="X", ...)` call. For each call:
    - If `X` is an intent (`LOG_FOOD`, `QUERY_DAILY_STATS`, `QUERY_FOOD_INFO`, `CHITCHAT`, `LOG_PERSONAL_STATS`) → change to `_make_state(user_intent="X", ...)`.
    - If `X` is a stage (`LOGGED`, `FAILED`, `NO_MATCH`, `CONFIRMED`, `REJECTED`, `AWAITING_CONFIRMATION`) → change to `_make_state(user_intent="LOG_FOOD", pipeline_stage="X", ...)` (existing intent for these LOG-stage tests).
    - If `X` is `""` (the empty-context test at line 178) → change to `_make_state(user_intent="", pipeline_stage="")`.
  - Walk every `assert parsed["last_action"] == "..."` line (~27 lines):
    - If the assertion is a duplicate of an existing `parsed["user_intent"]` / `parsed["pipeline_stage"]` check → drop the `last_action` line.
    - If the assertion was the only check on that turn → replace with the equivalent `parsed["user_intent"]` or `parsed["pipeline_stage"]` assertion.
  - Update the `test_empty_last_action` test (line 176) — rename to `test_empty_user_intent`, update the docstring and the assertion (`assert parsed["user_intent"] == ""`).
- **PATTERN**: The helper no longer auto-derives. Tests pass their fields explicitly. Boring and explicit beats clever.
- **GOTCHA**: This is the biggest test change in the PR. Worth running `uv run pytest tests/unit/test_response_node.py -v` repeatedly during the edit.
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v` — expect 25 passing.

### 17. UPDATE `tests/unit/test_confirmation_node.py` — drop assertions

- **IMPLEMENT**: At lines 253 and 276, drop `assert result.update["last_action"] == "..."` lines. Parallel `pipeline_stage` assertions exist.
- **VALIDATE**: `uv run pytest tests/unit/test_confirmation_node.py -v`.

### 18. UPDATE `tests/unit/test_commit_node.py` — drop assertion

- **IMPLEMENT**: At line 94, drop `assert result["last_action"] == "LOGGED"`. The parallel `assert result["pipeline_stage"] == "LOGGED"` exists.
- **VALIDATE**: `uv run pytest tests/unit/test_commit_node.py -v`.

### 19. UPDATE `tests/unit/test_personal_stats_node.py` — drop assertions

- **IMPLEMENT**: At lines 53 and 92, drop `assert result["last_action"] == "LOGGED"`.
- **VALIDATE**: `uv run pytest tests/unit/test_personal_stats_node.py -v`.

### 20. UPDATE `tests/unit/test_multi_item_loop.py` — drop assertions + state-setup

- **IMPLEMENT**: Drop assertions at lines 59 and 80. Drop state-setup `basic_state["last_action"] = "LOG_FOOD"` at line 152 (the parallel `basic_state["user_intent"] = "LOG_FOOD"` + `basic_state["pipeline_stage"] = "PENDING"` lines already exist).
- **VALIDATE**: `uv run pytest tests/unit/test_multi_item_loop.py -v`.

### 21. UPDATE `tests/unit/test_feedback_logic.py` — drop assertions

- **IMPLEMENT**: At lines 137 and 169, drop `assert result["last_action"] == "NO_MATCH"`. Parallel `pipeline_stage` assertions exist.
- **VALIDATE**: `uv run pytest tests/unit/test_feedback_logic.py -v`.

### 22. UPDATE `tests/unit/test_feedback_integration.py` — drop state-setup entries

- **IMPLEMENT**: At lines 52, 66, 84, 104, 123, drop the `"last_action": "..."` entries from each state-dict mock. Parallel `user_intent` / `pipeline_stage` entries already exist.
- **VALIDATE**: `uv run pytest tests/unit/test_feedback_integration.py -v`.

### 23. UPDATE `tests/unit/test_intent_stage_invariants.py` — drop legacy class + imports

- **IMPLEMENT**:
  - Drop the docstring lines about "legacy-fallback path" (lines 9-11).
  - Drop the `from src.agents.state import intent_from_legacy, stage_from_legacy` line (line 24).
  - Drop the `# last_action also dual-written for back-compat:` comment + `assert result["last_action"] == "QUERY_FOOD_INFO"` line in `test_query_food_info_intent_survives_through_parser` (~lines 86-89).
  - Drop the entire `TestLegacyCheckpointFallback` class (lines 126-160).
- **PATTERN**: `TestUserIntentImmutability` and `TestPipelineStageTransitions` cover the invariants that survive.
- **VALIDATE**: `uv run pytest tests/unit/test_intent_stage_invariants.py -v` — expect 5 passing (was 8).

### 24. UPDATE `tests/integration/test_log_yesterday_e2e.py` — drop state-setup entry

- **IMPLEMENT**: At line 78, drop `"last_action": "CONFIRMED",`. The parallel `"user_intent": "LOG_FOOD"` + `"pipeline_stage": "CONFIRMED"` entries already exist.
- **VALIDATE**: `uv run pytest tests/integration/test_log_yesterday_e2e.py -v` (requires Supabase DB).

### 25. VALIDATE Phase 2 — full unit + integration suites green

- **IMPLEMENT**: No code change. Verification step.
- **VALIDATE**:
  - `uv run pytest tests/unit/ -v` — expect ~190 passing (deleted 4 tests in Tasks 12 + 23, no failures).
  - `uv run pytest tests/integration/ -v` — expect 56 passing.
  - `grep -rn 'last_action\|GraphAction\|intent_from_legacy\|stage_from_legacy' src/ tests/ 2>/dev/null | grep -v __pycache__ | grep -v 'ux-loop\|\.txt'` — expect **zero results**.

### 26. UPDATE `docs/patterns/state-schemas.md`

- **IMPLEMENT**:
  - In the AgentState table (~line 45-56), drop the `last_action` row.
  - Drop the "Kept for one release" sentence from the paragraph that follows.
  - In the `GraphAction` bullet (~line 99), drop the bullet entirely. Keep the `UserIntent` and `PipelineStage` bullets.
  - In the `> [!note] Intent vs Stage (ADR-0005)` callout, adjust the wording — the historical "Pre-refactor, both were stored in a single `last_action` field" paragraph can stay (it's accurate history); the "Kept for one release" sentence should go.
- **VALIDATE**: `grep -n 'last_action\|GraphAction' docs/patterns/state-schemas.md` — expect only historical-context mentions (e.g. "Pre-refactor, …last_action…").

### 27. UPDATE `docs/adr/0005-split-user-intent-from-pipeline-stage.md` — reflect removal

- **IMPLEMENT**:
  - In the **Decision** section, change the paragraph about "kept for one release as a deprecated parallel field" → "Initially planned as a one-release deprecation window. During review of PR #32, the legacy-fallback layer was reassessed and found to never fire in practice (the resume path doesn't read the new fields; pre-refactor checkpoints store stage values that don't map to intents). The field, the `GraphAction` Literal, and the legacy-fallback helpers were removed in the same PR as a follow-up commit."
  - In **Alternatives considered §C (hard-cut migration)**, append a note: "**Reconsidered during PR #32 review and accepted.** See the Decision section."
  - In **Consequences → What this makes harder**, drop the "Two fields to keep consistent during deprecation" line.
  - In **Consequences → What we are committing to**, drop the "Removal of `last_action` is a tracked task" line and the surrounding paragraph.
- **PATTERN**: ADRs are immutable once accepted, but this one was Accepted 2026-05-11 (same day) and is materially incorrect about what shipped. Either edit in place (preferred — small enough that the history isn't lost) or add a "Postscript" section at the end. Edit in place per the simpler-is-better principle.
- **VALIDATE**: `grep -n 'last_action\|GraphAction\|intent_from_legacy\|stage_from_legacy' docs/adr/0005-split-user-intent-from-pipeline-stage.md` — expect only historical mentions in the Context section (the bug rationale).

### 28. UPDATE `docs/adr/DECISIONS.md` index entry

- **IMPLEMENT**: At the ADR-0005 entry, edit the one-liner. Change "`last_action` is kept dual-written for one release as a deprecated alias" → "`last_action`, `GraphAction`, and the legacy-fallback helpers were removed in the same PR".
- **VALIDATE**: `grep -n 'last_action\|GraphAction' docs/adr/DECISIONS.md` — single line, the updated one-liner.

### 29. UPDATE `docs/plans/split-user-intent-from-pipeline-stage-review-guide.md`

- **IMPLEMENT**:
  - Add a `> [!note] Update YYYY-MM-DD` callout at the very top: "The original PR included a one-release deprecation window keeping `last_action` as a dual-written field. On reassessment during review, that layer was removed in a follow-up commit on the same branch. The diff size below is post-removal; ignore any mention of dual-write or legacy helpers in the prose."
  - Walk the body of the guide and either remove or shorten references to: `intent_from_legacy`, `stage_from_legacy`, "legacy fallback", "dual-write", "deprecated parallel field". Recommend short inline edits rather than a wholesale rewrite — the reading order is still correct.
- **PATTERN**: A review guide is a snapshot of the diff at review time. After the follow-up commit, the snapshot needs updating to match the new diff.
- **VALIDATE**: `grep -n 'dual-write\|legacy fallback\|intent_from_legacy\|stage_from_legacy\|deprecated parallel' docs/plans/split-user-intent-from-pipeline-stage-review-guide.md` — should return only references inside the historical "Why" section or callouts.

### 30. UPDATE `commit_logs/2026-05-11_22-43-48_split-user-intent-from-pipeline-stage.md` — add postscript

- **IMPLEMENT**: At the top of the file, immediately after the title, add:
  ```markdown
  > **Update YYYY-MM-DD:** On review, the `last_action` deprecation window described below was removed in a follow-up commit on the same branch. The dual-write, the legacy-fallback helpers, and `GraphAction` are gone. See `commit_logs/<NEW_COMMIT_LOG>` for the removal commit.
  ```
- **PATTERN**: Commit logs are append-only history — add a postscript, don't rewrite. (Per the brain repo's commit-skill convention.)
- **VALIDATE**: `head -5 commit_logs/2026-05-11_22-43-48_split-user-intent-from-pipeline-stage.md` — should show the update note.

### 31. CREATE `commit_logs/<TIMESTAMP>_remove-last-action-deprecation.md`

- **IMPLEMENT**: New commit log for this removal. Use `date +"%Y-%m-%d_%H-%M-%S"` for the filename. Content:
  ```markdown
  # refactor: remove `last_action` deprecation window

  ## Why

  PR #32 introduced `user_intent` + `pipeline_stage` and kept `last_action` as a dual-written deprecated alias for one release, intended to protect paused HITL checkpoints. On review, the back-compat layer was reassessed and found to never fire in practice:

  - The resume path (`confirmation_node`'s `interrupt()` continuation) doesn't read `user_intent` or `pipeline_stage`. The fields the resume actually reads (`pending_confirmations`, `log_food`, `processing_results`) were unchanged by the refactor.
  - Routers run only on fresh turns. Fresh turns always run the parser first, which writes `user_intent`. The `or *_from_legacy(...)` fallback never fires.
  - `_build_context` could in theory use the fallback, but pre-refactor checkpoints store stage values in `last_action` (e.g. `AWAITING_CONFIRMATION`) — `intent_from_legacy` returns `None` for those, so the fallback is a no-op even in the one scenario it was designed for.

  Keeping the layer cost: dual review burden, 30+ lines across 12 files, a "DEPRECATED" flag in every node return. Removing it: zero loss of functionality, smaller diff for reviewers.

  ## What changed

  - Dropped `last_action` from every node return dict (6 nodes, 12 sites).
  - Dropped `GraphAction` Literal, `_INTENT_VALUES` / `_STAGE_VALUES` sets, `intent_from_legacy` / `stage_from_legacy` helpers, and the `get_args` import from `src/agents/state.py`.
  - Dropped the `last_action: GraphAction` field declaration from `AgentState`.
  - Simplified the three routers in `nutritionist.py` to read new fields directly (no `or *_from_legacy(...)` chain).
  - Simplified `_build_context` in `response_node.py` — direct reads, dropped `last_action` from JSON context, updated docstring.
  - Updated `tests/conftest.py::basic_state` to drop `"last_action": ""`.
  - Dropped `TestGraphActionIntegrity` (`test_state_consistency.py`) and `TestLegacyCheckpointFallback` + the back-compat assertion in `TestUserIntentImmutability` (`test_intent_stage_invariants.py`).
  - Rewrote `tests/unit/test_response_node.py::_make_state` without legacy auto-derive; migrated 27 `parsed["last_action"]` assertions and 20+ `_make_state(last_action=...)` calls to use the new fields directly.
  - Dropped `last_action` assertions across 8 writer test files (parallel new-field assertions added in PR #32 already cover the same surface).
  - Dropped `last_action` state-setup entries from 4 test files.
  - Updated `docs/patterns/state-schemas.md`, ADR-0005, `docs/adr/DECISIONS.md`, the review guide, and the original commit log to reflect the actual landed shape.

  ## Validation

  | Level | Command | Result |
  |---|---|---|
  | Lint | `uv run ruff check .` | ✅ |
  | Unit | `uv run pytest tests/unit/ -v` | ✅ ~190 passing |
  | Integration | `uv run pytest tests/integration/ -v` | ✅ 56 passing |
  | E2E | `uv run pytest tests/graph_api/ -v -s` | ✅ 15 passing |
  | Hygiene | `grep -rn 'last_action\|GraphAction\|intent_from_legacy\|stage_from_legacy' src/ tests/` | ✅ zero results |

  ## What's next

  - **`brain/TASKS.md` follow-up** — mark the "Remove `last_action`" Maintenance entry as ✅ with this PR reference.
  - **No outstanding cleanup** — the only deferred work tracked by ADR-0005 is the `NO_MATCH` overload disambiguation (split into `SELECTION_NO_MATCH` vs `MACRO_CALCULATION_FAILED`).
  ```
- **VALIDATE**: File exists and renders cleanly in Obsidian / Markdown preview.

### 32. UPDATE `brain/TASKS.md` (separate repo) — close the maintenance follow-up

- **IMPLEMENT**: In the brain repo's `TASKS.md` Maintenance section, find the "Remove `last_action` from `AgentState`" entry (around the section added by PR #32). Mark it ✅ with today's date and the PR reference: `✅ 2026-05-12 — folded into PR #32 same-branch follow-up commit. <link to commit hash>`.
- **GOTCHA**: This is a separate Git repo (the brain submodule). Edit it from inside `brain/`. The Obsidian Git plugin auto-commits on a ~10-min cadence, so don't worry about staging — just make the edit and it syncs.
- **VALIDATE**: `grep -n "Remove .last_action" brain/TASKS.md` — should show the completed entry.

### 33. VALIDATE Phase 4 — full validation suite, end-to-end

- **IMPLEMENT**: No code change. Final gate.
- **VALIDATE**:
  - `uv run ruff check .` — all checks passed.
  - `uv run pytest tests/unit/ -v` — ~190 passing.
  - `uv run pytest tests/integration/ -v` — 56 passing.
  - `uv run pytest tests/graph_api/ -v -s` — 15 passing (real LLM, ~2 min). Includes `TestQueryFoodInfoPath::test_query_food_info_does_not_commit` — the regression test for the silent-commit fix. This MUST stay green; if it fails, the new-field-only routing has a regression.
  - Final hygiene: `grep -rn 'last_action\|GraphAction\|intent_from_legacy\|stage_from_legacy' src/ tests/ docs/patterns docs/adr prompts/ notebooks/evals/ 2>/dev/null | grep -v __pycache__ | grep -v '\.txt\|ux-loop'` — should return ONLY:
    - Historical "Pre-refactor" mentions in `docs/patterns/state-schemas.md`, ADR-0005, the review guide, and the original commit log.
    - The plan file (`docs/plans/split-user-intent-from-pipeline-stage.md`) — historical plan, fine.
    - This plan file (`docs/plans/remove-last-action-deprecated-field.md`) — also fine.
  - No mentions in source code, tests, or active config.

### 34. COMMIT — atomic removal commit on the same branch

- **IMPLEMENT**: Stage every changed file explicitly. Don't `git add .`. Commit with a `refactor:` tag, HEREDOC body referencing the original commit hash + this plan + the new commit log.

  Commit message:
  ```
  refactor(state): remove last_action deprecation; clean shape from the start

  PR #32's commit a5c54c4 kept last_action as a dual-written deprecated
  alias for one release intended to protect paused HITL checkpoints. On
  review, the back-compat layer was reassessed and found to never fire in
  practice — the resume path doesn't read the new fields; pre-refactor
  checkpoints store stage values that don't map to intents.

  Removes last_action from state, all 6 writer nodes, both routers, and
  _build_context. Drops GraphAction Literal, intent_from_legacy/
  stage_from_legacy helpers, and the get_args import. Migrates tests to
  the new fields directly. Updates ADR-0005, the review guide, the
  original commit log, and brain/TASKS.md to reflect the actual landed
  shape (no deprecation window).

  Behavior-neutral cleanup. 197 unit + 56 integration + 15 E2E all green.
  TestQueryFoodInfoPath stays green (the regression test for the silent-
  commit fix is unaffected by the cleanup).

  Plan: docs/plans/remove-last-action-deprecated-field.md
  Original: a5c54c4 refactor(state): split last_action into user_intent...

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  ```
- **GOTCHA**: The PR is already open. After committing locally, `git push` will update the PR automatically — no new PR needed. Don't force-push (no need; we're adding a commit, not rewriting history).
- **VALIDATE**: `git log -2 --oneline` shows both the original PR #32 commit and the new removal commit on the same branch.

---

## TESTING STRATEGY

### Unit Tests

After removal, expect **~190 unit tests passing** (down from 197 due to removing `TestGraphActionIntegrity` = 1 test, `TestLegacyCheckpointFallback` = 3 tests, and `test_empty_last_action` renamed but functionally retained = net 0 from that file).

No new unit tests needed. The cleanup is mechanical — the existing invariant tests (`test_intent_stage_invariants.py::TestUserIntentImmutability`, `TestPipelineStageTransitions`, and the disjoint test in `test_state_consistency.py`) continue to enforce the contract the new shape relies on.

### Integration Tests

`tests/integration/test_log_yesterday_e2e.py` had one `last_action` state-setup line removed (Task 24). The rest of the integration suite is untouched. Expect 56 passing.

### Graph-API E2E Tests

The 15 E2E tests in `tests/graph_api/test_graph_flows.py` are unchanged. They don't reference `last_action`. The critical one — `TestQueryFoodInfoPath::test_query_food_info_does_not_commit` — proves the silent-commit fix is unaffected by the cleanup. Run it specifically to gate: `uv run pytest tests/graph_api/test_graph_flows.py::TestQueryFoodInfoPath -v -s`.

### Edge Cases

- **`get_args` import in `state.py` removal.** Verify no other module imports `get_args` from `src.agents.state` (the canonical location is `typing` directly). `grep -rn 'from src.agents.state import.*get_args' src/ tests/` should return zero.
- **Tests that explicitly populate `last_action: ""`.** None should remain after Task 25's grep. If any do, they'll silently work but emit a deprecation-implying field name.
- **The `tests/ux-loop/` trace artifacts.** These are historical traces from a prior UX-loop session and contain `last_action` keys in JSON. Leave them — they're snapshots of past state, not active code or test assertions.
- **Docstring scrub.** `docs/patterns/state-schemas.md` retains a historical "Pre-refactor, both were stored in a single `last_action` field" sentence. That's accurate history; leave it. Same for ADR-0005's Context section.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
uv run ruff check .
```

Expected: `All checks passed!`

### Level 2: Unit Tests

```bash
uv run pytest tests/unit/ -v
```

Expected: ~190 passing, zero failures.

### Level 3: Integration Tests

```bash
uv run pytest tests/integration/ -v
```

Expected: 56 passing.

### Level 4: Graph-API E2E

```bash
uv run pytest tests/graph_api/ -v -s
```

Expected: 15 passing including `TestQueryFoodInfoPath` (real LLM, ~2 min).

### Level 5: Hygiene grep

```bash
grep -rn 'last_action\|GraphAction\|intent_from_legacy\|stage_from_legacy' \
  src/ tests/ docs/patterns/ docs/adr/ prompts/ notebooks/evals/ 2>/dev/null \
  | grep -v __pycache__ \
  | grep -v 'ux-loop\|\.txt\|\.jsonl' \
  | grep -v 'docs/plans/'
```

Expected: only historical-context mentions in `docs/patterns/state-schemas.md`, `docs/adr/0005-...`, `docs/plans/split-user-intent-from-pipeline-stage-review-guide.md`, and the original commit log. Zero references in `src/`, `tests/`, `prompts/`, or `notebooks/evals/`.

### Level 6: Smoke test via dev bot (optional)

Same 5 scenarios from PR #32 — confirm no regression. If you ran them once, no need to re-run unless you specifically want to spot-check.

---

## ACCEPTANCE CRITERIA

- [ ] `src/agents/state.py` has no `GraphAction`, `last_action`, `intent_from_legacy`, `stage_from_legacy`, or `_INTENT_VALUES` / `_STAGE_VALUES`. `get_args` is no longer imported.
- [ ] No `last_action` key in any node return dict (6 nodes).
- [ ] Routers in `nutritionist.py` read `state.get("user_intent")` / `state.get("pipeline_stage")` directly with no fallback.
- [ ] `_build_context` reads new fields directly, doesn't emit `last_action` in JSON, docstring updated.
- [ ] `tests/conftest.py::basic_state` has no `last_action` key.
- [ ] `TestGraphActionIntegrity` and `TestLegacyCheckpointFallback` test classes removed.
- [ ] `tests/unit/test_response_node.py::_make_state` rewritten without legacy auto-derive; 27 assertions migrated to new fields.
- [ ] 8 writer test files have parallel `last_action` assertions removed.
- [ ] 4 state-setup files have `last_action` entries removed.
- [ ] `docs/patterns/state-schemas.md` reflects the removed deprecation window.
- [ ] ADR-0005 Decision section reflects "removed in same PR".
- [ ] DECISIONS.md index one-liner updated.
- [ ] Review guide has the Update callout at the top + body cleaned of dual-write language.
- [ ] Original commit log has the postscript Update note.
- [ ] New commit log created in `commit_logs/`.
- [ ] `brain/TASKS.md` Maintenance entry for last_action removal is marked ✅.
- [ ] All validation levels (Level 1–5) pass.

---

## COMPLETION CHECKLIST

- [ ] All 34 tasks completed in order.
- [ ] Each task's `VALIDATE` command run and green.
- [ ] All validation levels executed successfully.
- [ ] Full test suite passes (unit + integration + graph-api).
- [ ] No linting or type errors.
- [ ] Hygiene grep returns zero non-historical references.
- [ ] Commit landed on same branch (`refactor/split-user-intent-pipeline-stage`).
- [ ] `git push` updates PR #32 automatically.
- [ ] PR description optionally updated to mention the follow-up commit (gh pr edit; not strictly required).

---

## NOTES

### Risk profile

This is the **lowest-risk type of refactor**: pure deletion of a deprecated layer that has no production users (the field went in yesterday; no checkpoints exist yet referencing it). The blast radius is entirely internal — no API change, no schema change, no behavior change.

The single thing that could go wrong: a test relies on `last_action` being a specific value in a way that the parallel `user_intent` / `pipeline_stage` assertions don't cover. The Task 16 walk of `test_response_node.py` is the most exposure to that; running the suite incrementally during edits catches it.

### Confidence Score

**Confidence: 9/10** for one-pass execution success.

Risks:
- **Task 16's manual walk** of 27 assertions and 20+ `_make_state` calls — mechanical but bulky. Easy to miss one and have a test fail. Mitigated by running pytest after each meaningful batch of edits.
- **ADR-0005 rewrite** is a judgment call about how to acknowledge the reversed alternative §C. The plan recommends in-place edit with a "Reconsidered" note; an alternative is a "Postscript" section. Either works.

What pulls confidence up:
- Pure deletion, no new behavior to verify.
- The new-field assertions already exist in tests (added in PR #32) — we're removing the old assertions, not adding new ones.
- The E2E suite is unaffected — it doesn't reference `last_action`.
- The cleanup is a stated follow-up task in `brain/TASKS.md` Maintenance — we're just doing it now instead of in 2 weeks.

### Ship Strategy

**Same-branch follow-up commit on `refactor/split-user-intent-pipeline-stage`.**

1. Make the changes, commit locally.
2. `git push` — updates PR #32 automatically. No new PR needed.
3. CI re-runs on the new commit (lint + unit + integration). E2E manual via workflow_dispatch as before.
4. Optionally `gh pr edit 32` to add a note to the PR description: "Update: same-branch follow-up commit removes the `last_action` deprecation window — see commit `<hash>`."

If you'd rather have the cleanup as a separate PR on top of #32:
- Less clean (two PRs for a logically-unified change).
- More work for the reviewer (two diffs to context-switch between).
- Doesn't match the user's stated intent of "fold into this PR".

The same-branch follow-up is the right approach.

### Out of Scope (Explicit)

- The `NO_MATCH` overload disambiguation. Still tracked separately in `brain/TASKS.md` Maintenance.
- Touching `tests/ux-loop/` historical trace files (they're snapshots).
- Renaming `PipelineStage` or `UserIntent`.
- Removing `GraphAction` from `docs/plans/split-user-intent-from-pipeline-stage.md` (the original plan — keep as historical record).

### Why same-day reversal is OK

ADR-0004's "Revisit trigger" framing applies in spirit: a decision should be reopened when reality shows the assumption was wrong. ADR-0005's deprecation-window assumption was: "paused HITL checkpoints might fail to resume cleanly without the back-compat layer." Re-tracing the resume path showed that assumption was incorrect. Reopening and reversing within hours, with the original code still on a feature branch, is the cleanest possible feedback loop — there's no production cost.

The ADR gets edited in place because it was Accepted but not merged; the only place it's been read is by the author and a reviewer. Future readers will see the corrected version, with the Decision section noting the reversal.
