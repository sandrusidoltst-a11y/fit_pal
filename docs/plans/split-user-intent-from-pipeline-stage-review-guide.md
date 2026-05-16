# PR Reading Guide — split `last_action` into `user_intent` + `pipeline_stage`

> [!note] Update 2026-05-12
> This guide was written for the first commit on this branch, which kept `last_action` as a dual-written deprecated alias for one release. On reassessment during review, the back-compat layer was found to never fire in practice and was removed in a follow-up commit on the same branch. **Ignore any mention below of "dual-write", "legacy fallback", `intent_from_legacy` / `stage_from_legacy`, or `last_action` writes** — those references describe the intermediate state and not the final diff. The new state shape is `user_intent` + `pipeline_stage` only; `last_action` and `GraphAction` are gone. See `commit_logs/2026-05-12_08-33-08_remove-last-action-deprecation.md` for the removal commit.

This PR is 30 files large but conceptually simple if you read it in the right order. The change has one keystone (the new state shape), one writer that creates it, several readers that consume it, and a tail of tests and docs. Reading top-down by file path will be slow; this order takes ~15 minutes.

## Start here (intent)

1. **`commit_logs/2026-05-11_22-43-48_split-user-intent-from-pipeline-stage.md`** — what changed and why, in prose. Skim before any code.
2. **`docs/adr/0005-split-user-intent-from-pipeline-stage.md`** — the decision record. Specifically the *Alternatives considered* section — the choices it does NOT make (shadow field, substate-as-discriminator, hard-cut migration, two-PR ship) explain why the diff looks the way it does.
3. **`docs/plans/split-user-intent-from-pipeline-stage.md`** — the 30-task plan that produced the PR. Skim if you want to verify executor adherence; skip otherwise. The plan reads like a checklist; the diff is the answer key.
4. *(Optional)* **`brain/planning/query-food-info-routing-latent-bug.md`** (in the brain repo, not in this PR) — the motivating bug. Helpful if "QUERY_FOOD_INFO silent-commit risk" isn't obvious.

## The keystone

5. **`src/agents/state.py`** — read this first among the code files. Two new `Literal` types (`UserIntent`, `PipelineStage`) and two new `AgentState` fields (`user_intent`, `pipeline_stage`). `GraphAction` is kept as a deprecated union. Also defines two legacy-fallback helpers (`intent_from_legacy`, `stage_from_legacy`) that map old `last_action` values back to the new fields — these protect paused HITL checkpoints whose state predates the refactor. **If you only read one file, read this one.** Every other diff is downstream.

## The writer (intent is born)

6. **`src/schemas/input_schema.py`** — one-line rename: Pydantic `UserIntent` → `UserIntentEvent`. Frees the natural name for the new Literal. Follows ADR-0004's `Event` suffix convention.
7. **`src/agents/nodes/input_node.py`** — the **sole writer of `user_intent`**. Three changes: import update for the Pydantic rename, `with_structured_output(UserIntentEvent)`, and a 3-line addition to the return dict (`user_intent`, `pipeline_stage="PENDING"`, dual-written legacy `last_action`).

## The stage writers (5 nodes, mechanical dual-write)

8. **`src/agents/nodes/selection_node.py`** — 5 return sites, each gets `"pipeline_stage": <same value as last_action>`.
9. **`src/agents/nodes/calculate_macros_node.py`** — 2 return sites.
10. **`src/agents/nodes/confirmation_node.py`** — 2 sites inside `Command.update` dicts.
11. **`src/agents/nodes/commit_node.py`** — 1 site.
12. **`src/agents/nodes/personal_stats_node.py`** — 1 site.

Reviewer note: these are 5 nearly-identical edits. Reading one is reading all. Skim the others.

## The readers (where intent and stage are consumed)

13. **`src/agents/nutritionist.py`** — three router functions, this is the part that fixes the bug:
    - `route_parser` reads `user_intent` (with legacy fallback).
    - `route_after_selection` reads `pipeline_stage` (with legacy fallback).
    - `route_after_calculate_macros` — **NEW BRANCH**: when `user_intent == "QUERY_FOOD_INFO"`, route to `load_daily_context` (skip confirmation + commit). The conditional-edges map gains a `load_daily_context` entry.
14. **`src/agents/nodes/response_node.py`** — `_build_context` rewritten to dispatch on `user_intent`. New branch for `QUERY_FOOD_INFO` surfaces `pending_confirmations` as `queried_foods` so the LLM has DB-grounded macros. Keeps `last_action` in the emitted JSON for one release for prompt back-compat.

## Adjacent — prompt and docs

15. **`prompts/response_generator.md`** — two changes: dispatch rule at line 27 references `user_intent` instead of `last_action`; new "Nutrition Q&A" section governs how the LLM answers when `queried_foods` is present. The explicit rule against logging language ("I logged", "want me to log it?") is the human side of the routing fix.
16. **`docs/patterns/state-schemas.md`** — `AgentState` field table updated; new paragraph explaining the split.
17. **`docs/adr/DECISIONS.md`** — ADR-0005 index entry.

## Tests — regression guards first, then the migration tail

18. **`tests/graph_api/test_graph_flows.py::TestQueryFoodInfoPath`** — **THE regression test**. Sends "How much protein is in 100g of chicken?" through the real langgraph dev server. Snapshots `daily_logs` row count for the test user before and after the run; asserts zero new rows. If this test passes, the silent-commit risk is closed. **Read this test as documentation for what the bug fix is supposed to prove.**
19. **`tests/unit/test_intent_stage_invariants.py`** *(NEW FILE)* — 8 tests across three classes:
    - `TestUserIntentImmutability` — verifies downstream nodes don't return `user_intent` in their dict (so LangGraph's partial merge preserves the parser's value).
    - `TestPipelineStageTransitions` — each writer node emits the expected stage value.
    - `TestLegacyCheckpointFallback` — `intent_from_legacy` / `stage_from_legacy` map correctly; the two value sets are disjoint.
20. **`tests/unit/test_state_consistency.py`** — three new test classes verify `UserIntent` matches `ActionType` exactly, `PipelineStage` covers all expected stages, and the two Literals are **disjoint by construction**. This last assertion is the type-level safety net.
21. **`tests/unit/test_response_node.py`** — `_make_state(**overrides)` helper auto-derives the new fields from the legacy `last_action` value. **This is the load-bearing test change**: it's how the 27 existing assertions on `parsed["last_action"]` keep passing without per-test edits.
22. **8 writer test files** — `test_input_parser.py`, `test_agent_selection.py`, `test_calculate_macros_node.py`, `test_confirmation_node.py`, `test_commit_node.py`, `test_personal_stats_node.py`, `test_multi_item_loop.py`, `test_feedback_logic.py`. Each gets parallel assertions on `user_intent` and/or `pipeline_stage` alongside the existing `last_action` assertions. Mechanical — reading one is reading all.
23. **`tests/unit/test_feedback_integration.py`** — state-setup style: 5 dict literals get the new fields populated.
24. **`tests/integration/test_log_yesterday_e2e.py`** — same: state setup at line 78 gets `user_intent` + `pipeline_stage`.
25. **`tests/conftest.py`** — `basic_state` fixture extended with the new fields.

## Evals

26. **`notebooks/evals/eval_input_parser_hebrew.py`** & **`eval_input_parser.ipynb`** — one-line change: `result["last_action"]` → `result["user_intent"]`. Datasets unaffected.

---

## Things worth flagging while reviewing

1. **`last_action` is intentionally kept** as a deprecated dual-written field for one release. It feels like dead weight on first read, but removing it would break paused HITL checkpoints whose Postgres state predates this deploy. Removal is tracked as a follow-up Maintenance task in `brain/TASKS.md`. ADR-0005's *Alternatives considered* section §C explains why hard-cut migration was rejected.

2. **`_build_context` edge case for pre-refactor checkpoints** (Task 14 GOTCHA in the plan). If a paused thread's checkpoint has `last_action="LOGGED"` (a stage, not an intent), `intent_from_legacy` returns `None` → `_build_context` falls into the minimal-context path → response is generic without naming the food. Acceptable tax: affects ~30 min of paused threads at deploy time and self-heals on the next fresh message. Worth confirming you'd accept that vs. building a substate-presence-based derivation.

3. **`_make_state` helper auto-derive logic** (`test_response_node.py`). When a test passes `last_action="LOGGED"` (a stage), the helper defaults `user_intent="LOG_FOOD"` because every existing test that passes a stage value is simulating a LOG flow. When `last_action=""` (the empty-context test case), `user_intent` stays `""`. That branching keeps existing assertions green without per-test edits — but it's a touch clever. If you'd rather see explicit `user_intent` passed to every test, that's a defensible alternative; the trade is 27 mechanical test edits.

4. **The Pydantic class rename** (`UserIntent` → `UserIntentEvent`) is scoped tightly (3 touchpoints) but it does ripple into a generic name. The new Literal taking the natural name pays for the rename. If you'd rather have called the Literal `IntentLabel` and left the Pydantic class alone, that's the alternative I rejected — see ADR-0005 *Decision* and the plan's Open Question #1.

5. **`response_node._build_context` still emits `last_action` in the JSON context** for one release. The new prompt sections use `user_intent`, but the legacy fields are kept as a compatibility belt in case the LLM has prompt-side dependencies we missed. Goes away with the `last_action` removal task.

6. **Brain TASKS.md update is auto-committed by the Obsidian Git plugin** (separate repo, not in this diff). The Important #2 entry is marked complete with reference to this PR; two new Maintenance tasks are tracked there. If you want to see it, browse the `brain/` submodule path — it's not part of this fit_pal commit.

## Skip-able

These files have low signal-per-line — skim or skip:

- **8 writer test files in `tests/unit/`** — repetitive parallel-assertion additions. Read one (e.g. `test_input_parser.py`), the rest follow the same pattern.
- **`tests/unit/test_feedback_integration.py`** — 5 mechanical state-dict updates.
- **`notebooks/evals/eval_input_parser.ipynb`** — the diff looks ugly because it's a JSON notebook; only one cell changed (the `run_input_parser` function, swapping `result["last_action"]` → `result["user_intent"]`). The `.py` sibling shows the same change in readable form.
- **`tests/conftest.py`** — 2 lines added to a fixture.
- **`tests/integration/test_log_yesterday_e2e.py`** — 2 lines added to a state dict.
