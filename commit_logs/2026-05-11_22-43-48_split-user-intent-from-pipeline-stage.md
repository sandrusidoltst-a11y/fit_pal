# refactor: split `last_action` into `user_intent` + `pipeline_stage`; route `QUERY_FOOD_INFO` past commit

## Why

`AgentState.last_action` was a single `Literal` field doing two unrelated jobs:

1. **User intent** — what the user originally asked for (`LOG_FOOD`, `QUERY_FOOD_INFO`, `QUERY_DAILY_STATS`, `CHITCHAT`, `LOG_PERSONAL_STATS`). Set by `input_parser_node`.
2. **Pipeline stage** — where the graph is in processing that intent (`SELECTED`, `NO_MATCH`, `AMBIGUOUS`, `AWAITING_CONFIRMATION`, `CONFIRMED`, `REJECTED`, `LOGGED`). Overwritten by every downstream node.

Three symptoms forced the split:

- **Latent `QUERY_FOOD_INFO` silent-commit risk** (TASKS.md Important #2). The user asks "how much protein is in an egg?", parser classifies as `QUERY_FOOD_INFO`, routing sends it through the full LOG pipeline ending in a HITL "log this egg?" prompt for a question the user never asked as a log. Three cancelling bugs hide it today; fixing any one exposes it. The clean fix needs `if user_intent == "QUERY_FOOD_INFO"` somewhere after `calculate_macros` — impossible because by then `last_action` is `AWAITING_CONFIRMATION`. The originating intent is gone.
- **`response_node._build_context` over-generalization** — `if last_action in ("LOG_FOOD", "LOGGED", "FAILED", "NO_MATCH", "SELECTED", "CONFIRMED", "REJECTED")` mixed one intent value with six pipeline-stage values. Worked only because no other intent shared those stage names; brittle to any new flow.
- **`NO_MATCH` overload** — two different nodes set it for two different causes (`agent_selection_node` for search miss, `calculate_macros_node` for tool error). Disambiguation deferred to a follow-up; flagged here to be unblocked by the new shape.

See `docs/adr/0005-split-user-intent-from-pipeline-stage.md` for the full decision record and `brain/planning/query-food-info-routing-latent-bug.md` for the motivating bug.

## What changed

### State shape (`src/agents/state.py`)

Added two `Literal` types and two `AgentState` fields:

- `UserIntent` Literal — mirrors `ActionType` exactly (5 values).
- `PipelineStage` Literal — 8 values (`PENDING` + 7 existing stage markers).
- `user_intent: UserIntent` — written once by the parser; immutable for the turn.
- `pipeline_stage: PipelineStage` — overwritten freely by intermediate nodes; initialized to `PENDING` at turn start.

`UserIntent` and `PipelineStage` are **disjoint by construction** — enforced by a new `TestIntentStageDisjoint` test.

`last_action: GraphAction` is kept as a deprecated parallel field for one release. Two legacy-fallback helpers (`intent_from_legacy`, `stage_from_legacy`) map old `last_action` values back to the new fields so paused HITL checkpoints (whose Postgres state predates this refactor) resume safely. Removal tracked as a follow-up Maintenance task.

### Pydantic class rename (`src/schemas/input_schema.py`)

`UserIntent` (the structured-output wrapper around the discriminated union) → `UserIntentEvent`. Follows ADR-0004's `Event` suffix convention and frees the natural name for the new Literal. Three touchpoints: schema file, `input_node.py` import, `input_node.py` `with_structured_output` call.

### Writer nodes — dual-write

Six nodes that wrote `last_action` now dual-write the same value to the appropriate new field, **without removing the legacy field**:

| Node | Writes |
|---|---|
| `input_node.py` | `user_intent = result.action.value`, `pipeline_stage = "PENDING"` |
| `selection_node.py` | `pipeline_stage = "SELECTED" \| "NO_MATCH"` (5 sites) |
| `calculate_macros_node.py` | `pipeline_stage = "AWAITING_CONFIRMATION" \| "NO_MATCH"` |
| `confirmation_node.py` | `pipeline_stage = "CONFIRMED" \| "REJECTED"` (in `Command.update`) |
| `commit_node.py` | `pipeline_stage = "LOGGED"` |
| `personal_stats_node.py` | `pipeline_stage = "LOGGED"` |

Only `input_node` writes `user_intent`. Every other node leaves it alone — verified by a new `TestUserIntentImmutability` test.

### Readers — migrated to new fields with legacy fallback

- `nutritionist.py::route_parser` — reads `user_intent` (with fallback).
- `nutritionist.py::route_after_selection` — reads `pipeline_stage` (with fallback).
- `nutritionist.py::route_after_calculate_macros` — **NEW BRANCH**: when `user_intent == "QUERY_FOOD_INFO"`, route to `load_daily_context` (skip `confirmation` + `commit`). This is the routing fix that closes the silent-commit risk.
- `response_node._build_context` — dispatches on `user_intent` for "which flow"; emits `queried_foods` (DB-grounded macros from `pending_confirmations`) when intent is `QUERY_FOOD_INFO` so the LLM has real values to answer with.

### Prompt (`prompts/response_generator.md`)

- Renamed `last_action` → `user_intent` in the dispatch rules at line 27.
- New `Nutrition Q&A` section: when `user_intent` is `QUERY_FOOD_INFO` and `queried_foods` is present, answer with those macros. Explicit rule against logging language ("I logged", "I'll add this", "want me to log it?"). Hedge if `source: "estimated"`.

### Tests (12 files touched, 1 new file)

- **`tests/conftest.py::basic_state`** — fixture extended with `user_intent: ""`, `pipeline_stage: ""` defaults.
- **`tests/unit/test_state_consistency.py`** — three new test classes: `TestUserIntentIntegrity` (matches `ActionType`), `TestPipelineStageIntegrity` (covers `SelectionStatus` + HITL + `LOGGED` + `PENDING`), `TestIntentStageDisjoint` (the disjoint invariant).
- **`tests/unit/test_intent_stage_invariants.py`** — NEW. 8 tests across three classes:
  - `TestUserIntentImmutability` — selection_node does not return `user_intent` (proves immutability via LangGraph partial merge); parser sets `user_intent="QUERY_FOOD_INFO"`.
  - `TestPipelineStageTransitions` — each writer node emits the expected stage value.
  - `TestLegacyCheckpointFallback` — `intent_from_legacy`/`stage_from_legacy` map correctly; disjoint property holds in legacy mapping.
- **8 writer test files** — parallel assertions on `user_intent` and/or `pipeline_stage` alongside existing `last_action` assertions (verifies dual-write integrity).
- **`tests/unit/test_response_node.py::_make_state`** — helper extended to auto-derive new fields from legacy `last_action` so the existing 27 assertions on `parsed["last_action"]` continue to pass without per-test edits.
- **`tests/integration/test_log_yesterday_e2e.py`** — state setup at line 78 now includes `user_intent` + `pipeline_stage`.
- **`tests/graph_api/test_graph_flows.py::TestQueryFoodInfoPath`** — NEW E2E. Sends "How much protein is in 100g of chicken?" through the real langgraph dev server. Three assertions:
  1. Graph does NOT pause at HITL interrupt.
  2. `daily_logs` row count for the test user is **unchanged** before/after the run (real DB snapshot via `AsyncSessionLocal`, not the transactional test session). THE regression test.
  3. Response is non-empty and references macros.

### Evals (`notebooks/evals/`)

- `eval_input_parser_hebrew.py:454` and `eval_input_parser.ipynb` cell 5 — `result["last_action"]` → `result["user_intent"]`. Datasets unaffected (the field is an output label, not a dataset input).

### Docs

- **`docs/adr/0005-split-user-intent-from-pipeline-stage.md`** — full ADR. Captures context, alternatives considered (shadow field, substate-as-discriminator, hard-cut migration, two-PR ship), consequences, revisit triggers.
- **`docs/adr/DECISIONS.md`** — index entry added.
- **`docs/patterns/state-schemas.md`** — `AgentState` field table updated; new paragraph cross-referencing ADR-0005.
- **`brain/TASKS.md`** — Important #2 (QUERY_FOOD_INFO Silent-Commit Risk) marked complete with reference to this PR. Two new Maintenance tasks added: remove `last_action`, NO_MATCH overload disambiguation.

## How this fits the bigger picture

This is the third leg of the discriminated-action work started in ADR-0004 (PR #26). That PR introduced `LogFoodSubState` and `QueryStatsSubState` — per-action data carriers. This refactor adds the corresponding **per-turn intent discriminator**, completing the pattern: `user_intent` says which substate is meaningful; the substate holds the data; `pipeline_stage` says where in processing we are.

For the QUERY_FOOD_INFO routing fix specifically: no new substate was needed. The user's question doesn't carry extra data beyond `pending_food_items` and `pending_confirmations`. `user_intent == "QUERY_FOOD_INFO"` alone is sufficient as a gate.

## Validation

All four validation levels green:

| Level | Command | Result |
|---|---|---|
| Lint | `uv run ruff check .` | ✅ All checks passed |
| Unit | `uv run pytest tests/unit/ -v` | ✅ **197 passed** (was 185 pre-refactor) |
| Integration | `uv run pytest tests/integration/ -v` | ✅ 56 passed (real Supabase) |
| E2E | `uv run pytest tests/graph_api/ -v -s` | ✅ 15 passed (real LLM + real DB) |

The E2E `TestQueryFoodInfoPath` is the load-bearing test: it asserts zero new `daily_logs` rows after a nutrition Q&A turn against the production schema. That's the bug this PR closes.

## What's next

- **Deploy and monitor.** CI runs lint + unit + integration automatically; CD will redeploy on merge. Watch logs for 24 hours after deploy. Specifically: `BlockingError` (none expected), unexpected routes to `load_daily_context` for non-QUERY turns, prompt regressions where the LLM still uses logging voice for QUERY_FOOD_INFO turns.
- **Live UX validation.** Worth running the `/live-ux-loop` skill with a QUERY_FOOD_INFO scenario to confirm the prompt is actually answering with `queried_foods` and not falling back to chitchat-shaped guesses.
- **Remove `last_action` (~2 weeks post-deploy).** Tracked in `brain/TASKS.md` Maintenance. Drop the field, the dual-writes, the legacy helpers, the back-compat reads, the `GraphAction` Literal. Should be a small clean-up PR.
- **NO_MATCH overload disambiguation.** Now unblocked by the new shape — split `pipeline_stage="NO_MATCH"` into `SELECTION_NO_MATCH` (selection_node) vs `MACRO_CALCULATION_FAILED` (calculate_macros_node). Tracked in TASKS.md.

## References

- Plan: `docs/plans/split-user-intent-from-pipeline-stage.md` (30 ordered tasks, all executed)
- ADR: `docs/adr/0005-split-user-intent-from-pipeline-stage.md`
- Motivating bug: `brain/planning/query-food-info-routing-latent-bug.md`
- Related ADR: `docs/adr/0004-schema-to-state-translation-ownership.md` (substate pattern this extends)
