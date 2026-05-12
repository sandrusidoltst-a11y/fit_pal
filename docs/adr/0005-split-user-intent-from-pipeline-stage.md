# ADR-0005: Split `last_action` into `user_intent` + `pipeline_stage`

- **Status**: Accepted 2026-05-11
- **Area**: state, routing
- **Deciders**: Dolev (with Claude Opus 4.7)

## Context

`AgentState.last_action` was a single `Literal` field doing two unrelated jobs:

1. **User intent** — what the user originally asked for: `LOG_FOOD`, `QUERY_FOOD_INFO`, `QUERY_DAILY_STATS`, `CHITCHAT`, `LOG_PERSONAL_STATS`. Set by `input_parser_node`.
2. **Pipeline stage** — where the graph is in processing that intent: `SELECTED`, `NO_MATCH`, `AMBIGUOUS`, `AWAITING_CONFIRMATION`, `CONFIRMED`, `REJECTED`, `LOGGED`. Overwritten by each downstream node.

Every node that wrote a stage marker (`selection_node`, `calculate_macros_node`, `confirmation_node`, `commit_node`, `personal_stats_node`) erased the parser's intent value. By the time `route_after_calculate_macros` or `response_node._build_context` ran, the field held a stage marker — the originating intent was unrecoverable.

Three concrete symptoms forced the change:

1. **Latent `QUERY_FOOD_INFO` silent-commit risk (TASKS.md Important #2).** When the parser classifies a message as `QUERY_FOOD_INFO`, today's routing sends it through the full LOG pipeline ending in a HITL "log this?" prompt. Three cancelling bugs (parser empty items + `agent_selection` NO_MATCH + empty-batch shortcut in `confirmation_node`) coincide to skip the prompt today. Fixing any one of those exposes the bug. The clean fix needs `if user_intent == "QUERY_FOOD_INFO"` somewhere after `calculate_macros` — impossible because by then `last_action` is `AWAITING_CONFIRMATION`.
2. **`response_node._build_context` over-generalization.** The LOG flow gated on `if last_action in ("LOG_FOOD", "LOGGED", "FAILED", "NO_MATCH", "SELECTED", "CONFIRMED", "REJECTED")` — six pipeline-stage values mashed with one intent value. Worked only because no other intent used those stages. Adding `QUERY_FOOD_INFO` through `SELECTED`/`NO_MATCH` would silently misroute its context to the LOG branch.
3. **`NO_MATCH` overload.** Set by both `agent_selection_node` (search miss) and `calculate_macros_node` (tool error). Same string, different cause — minor smell today, harder to disambiguate as stages pile up. (Disambiguation deferred to a follow-up; see TASKS.md.)

The discriminated-action-state refactor (PR #26, 2026-05-06 — ADR-0004) already introduced per-action sub-states (`LogFoodSubState`, `QueryStatsSubState`). Splitting `last_action` continues that direction by separating intent (which sub-state is active) from stage (where in the pipeline).

## Decision

Split `last_action` into two `Literal` fields on `AgentState`:

- **`user_intent: UserIntent`** — written once by `input_parser_node`; not touched by any downstream node. Values: `LOG_FOOD`, `QUERY_FOOD_INFO`, `QUERY_DAILY_STATS`, `CHITCHAT`, `LOG_PERSONAL_STATS`. The new `UserIntent` Literal mirrors `ActionType` exactly.
- **`pipeline_stage: PipelineStage`** — overwritten freely by intermediate nodes. Values: `PENDING` (set by parser), `SELECTED`, `NO_MATCH`, `AMBIGUOUS`, `AWAITING_CONFIRMATION`, `CONFIRMED`, `REJECTED`, `LOGGED`.

The two value sets are **disjoint** by construction — tested in `tests/unit/test_state_consistency.py::TestIntentStageDisjoint`.

`last_action: GraphAction` is **kept** for one release as a deprecated parallel field. Every writer dual-writes (the old `last_action` value plus the new field). Readers (routers, `response_node._build_context`) read the new field with a legacy fallback (`intent_from_legacy` / `stage_from_legacy` in `src/agents/state.py`) that maps `last_action` back when the new fields are absent. This protects in-flight HITL-paused conversations whose Postgres checkpoints predate the refactor.

Naming: the pre-existing Pydantic class `UserIntent` (the structured-output wrapper) was renamed to `UserIntentEvent`, freeing the `UserIntent` name for the new Literal. The rename follows ADR-0004's `Event` suffix convention.

The QUERY_FOOD_INFO silent-commit fix ships **in the same PR** as the refactor. `route_after_calculate_macros` gates on `user_intent == "QUERY_FOOD_INFO"` and routes those turns to `load_daily_context` (skipping `confirmation` + `commit`); `response_node._build_context` surfaces `pending_confirmations` as `queried_foods` so the LLM answers with DB-grounded macros.

## Alternatives considered

### A. Keep `last_action` monolithic, add a shadow `originating_action` field

Add a second field that only the parser writes and nothing overwrites. Routers still read `last_action` for stage info, but late-stage nodes can also consult `originating_action` when they need to know the intent.

**Rejected because** it adds a field without fixing the conceptual mixing in `last_action`. `_build_context`'s six-value condition would still be there. The split is the same shape but only half-applied — readers would still have to choose between two conflated fields. Cleaner to make `last_action` itself two fields.

### B. Use sub-state presence as the discriminator

Discriminate by which sub-state TypedDict has values: `log_food` populated → intent is LOG_FOOD; `query_stats` populated → intent is QUERY_DAILY_STATS. Avoid adding a new field at all.

**Rejected because** it makes intent a derived property of other fields, which is fragile to future sub-state additions. The sub-states themselves were already considered for renaming/restructuring and adding a "presence flag" per sub-state would be its own awkwardness. Also: `CHITCHAT` and `LOG_PERSONAL_STATS` have no sub-state (no extra data to carry), so we'd still need an explicit field for those — at which point a single `user_intent` field is cleaner than two parallel discrimination patterns.

### C. Hard-cut migration — remove `last_action` and the legacy fallback in this PR

Just delete `last_action`. Force-resolve paused HITL threads at deploy time, or accept that in-flight users get an error on resume.

**Rejected because** paused HITL threads at deploy time would read state with an unknown shape. The cost of one release of dual-write is small (one extra field per node return); the cost of broken HITL resumes for users in the middle of a confirmation is real-user friction we don't need to take.

### D. Two separate PRs — refactor first, QUERY_FOOD_INFO fix second

Land the behavior-neutral refactor alone, watch logs for ~2 weeks, then land the QUERY_FOOD_INFO routing change in a follow-up.

**Rejected because** the user chose one PR after weighing the trade-offs. Rollback is `git revert` either way; the refactor's legacy-fallback design makes paused-checkpoint resume safe whether the QUERY_FOOD_INFO gate is present or not (the gate runs only on fresh turns after `calculate_macros`, not on HITL resume).

## Consequences

### What this makes easier

- **`QUERY_FOOD_INFO` routing is trivial.** `route_after_calculate_macros` reads `user_intent` and gates. The bug TASKS.md tracked as Important #2 is closed.
- **`response_node._build_context` is conceptually simpler.** Dispatch on `user_intent` for which flow we're in; use `pipeline_stage` for stage-specific rendering within that flow. The six-value `if last_action in (...)` soup is gone.
- **Future late-stage routers can read intent.** Anything we add after the parser can answer "what did the user ask for?" reliably, without depending on which node ran last.
- **The substate-pattern naming is consistent.** `UserIntent` Literal + `UserIntentEvent` Pydantic class + per-action sub-states all share the `User*`/`*Event`/`*SubState` triad from ADR-0004.

### What this makes harder

- **Two fields to keep consistent during deprecation.** Every writer dual-writes; future contributors might forget. Mitigation: `tests/unit/test_intent_stage_invariants.py` covers transitions and immutability; the test_state_consistency.py disjoint test catches Literal drift.
- **`_build_context` edge case on pre-refactor checkpoints.** If a paused HITL thread's checkpoint has `last_action="LOGGED"` (a stage, not an intent), the legacy fallback returns `intent=None` and `_build_context` renders a minimal context block. The user sees a generic "logged" response rather than one that names the food. Acceptable — affects only ~30 min of paused threads at deploy time; resolves on the next fresh message.
- **JSON context block is ~3 lines longer.** `user_intent`, `pipeline_stage`, AND `last_action` all emitted to the prompt. Negligible token cost; goes away when `last_action` is removed.

### What we are committing to

- **`user_intent` is immutable per turn.** Once `input_parser_node` writes it, no other node may overwrite it. New writer nodes added to the graph must not include `user_intent` in their return dict.
- **`pipeline_stage` is the only stage signal.** `last_action` is a deprecated alias for one release; new code should not read it.
- **Removal of `last_action` is a tracked task** (`brain/TASKS.md` Maintenance). The follow-up cleanup drops the field, the dual-writes, the legacy-fallback helpers, and the back-compat reads in routers and `_build_context`.

## Revisit trigger

Reopen this decision if either of the following occurs:

1. **`pipeline_stage` value set grows past ~10 distinct values OR a single value gets reused across intents.** Today the disjoint test enforces no overlap, but if stage values start needing intent-specific meanings (e.g., `LOGGED` for LOG_FOOD vs `LOGGED` for personal stats become semantically different), per-intent state machines may be cleaner than a single flat `PipelineStage` Literal.
2. **A drift incident ships.** A writer node forgets to dual-write or reads from the wrong field, and a bug reaches production. The discipline-only consistency is the weakest part of this design — one real failure is the signal that we should move the deprecation forward.

## Related

- **TASKS.md Important #2** — QUERY_FOOD_INFO Silent-Commit Risk (closed by this ADR's PR).
- **TASKS.md Maintenance** — *Remove `last_action` from AgentState* (after ~2 weeks).
- **TASKS.md Maintenance** — *NO_MATCH overload disambiguation* (split selection-miss vs macro-tool-error).
- **Plan**: `docs/plans/split-user-intent-from-pipeline-stage.md` — full 30-task implementation plan that produced this ADR.
- **Planning note**: `brain/planning/query-food-info-routing-latent-bug.md` — the bug that motivated the split.
- **ADR-0004** (`docs/adr/0004-schema-to-state-translation-ownership.md`) — the discriminated-action sub-state pattern this extends.
- **Code anchors**:
  - `src/agents/state.py` — `UserIntent`, `PipelineStage` Literals; `intent_from_legacy`, `stage_from_legacy` helpers.
  - `src/agents/nutritionist.py` — `route_parser`, `route_after_selection`, `route_after_calculate_macros` migrated.
  - `src/agents/nodes/input_node.py` — sole writer of `user_intent`.
  - `src/agents/nodes/response_node.py` — `_build_context` migrated; QUERY_FOOD_INFO branch added.
  - `prompts/response_generator.md` — references `user_intent`; adds Nutrition Q&A section.
  - `tests/unit/test_intent_stage_invariants.py` — refactor invariants.
  - `tests/unit/test_state_consistency.py` — Literal integrity tests.
  - `tests/graph_api/test_graph_flows.py::TestQueryFoodInfoPath` — E2E regression test (DB snapshot).
