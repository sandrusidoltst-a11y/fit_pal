# refactor: remove `last_action` deprecation window

## Why

The previous commit on this branch (`a5c54c4` — split `last_action` into `user_intent` + `pipeline_stage`) kept `last_action` as a dual-written deprecated alias for one release, intended to protect paused HITL checkpoints. On review, the back-compat layer was reassessed and found to never fire in practice:

- The resume path (`confirmation_node`'s `interrupt()` continuation) doesn't read `user_intent` or `pipeline_stage`. The fields the resume actually reads (`pending_confirmations`, `log_food`, `processing_results`) were unchanged by the refactor.
- Routers run only on fresh turns. Fresh turns always run the parser first, which writes `user_intent`. The `or *_from_legacy(...)` fallback never fires.
- `_build_context` could in theory use the fallback, but pre-refactor checkpoints store stage values in `last_action` (e.g. `AWAITING_CONFIRMATION`, `CONFIRMED`, `LOGGED`) — `intent_from_legacy` returns `None` for those, so the fallback is a no-op even in the one scenario it was designed for.

Keeping the layer cost: dual review burden (this PR and a follow-up cleanup PR ~2 weeks later), 30+ extra lines across 14 files, a "DEPRECATED" flag in every node return that invites confusion.

Removing it now: zero loss of functionality, smaller diff for reviewers, no deprecation tail to clean up. The hard-cut migration (originally Alternative §C in ADR-0005) is what we shipped.

## What changed

### Source code

- Dropped `last_action` from every node return dict (6 nodes, 12 sites): `input_node`, `selection_node`, `calculate_macros_node`, `confirmation_node`, `commit_node`, `personal_stats_node`.
- Dropped `GraphAction` Literal, the `_INTENT_VALUES` / `_STAGE_VALUES` sets, `intent_from_legacy` / `stage_from_legacy` helpers, and the `get_args` import from `src/agents/state.py`.
- Dropped the `last_action: GraphAction` field declaration from `AgentState`.
- Simplified the three routers in `nutritionist.py` to read new fields directly (no `or *_from_legacy(...)` chain). Dropped the corresponding imports.
- Simplified `_build_context` in `response_node.py` — direct reads of `user_intent` / `pipeline_stage`, dropped `last_action` entry from emitted JSON context, dropped legacy-helper imports, simplified docstring.

### Tests

- Updated `tests/conftest.py::basic_state` to drop `"last_action": ""`.
- Dropped `TestGraphActionIntegrity` from `test_state_consistency.py` (drift between `ActionType`/`SelectionStatus` and the deprecated union is no longer a concern).
- Dropped `TestLegacyCheckpointFallback` and the legacy-assertion in `TestUserIntentImmutability` from `test_intent_stage_invariants.py`. Removed legacy imports.
- Rewrote `tests/unit/test_response_node.py::_make_state` — dropped the auto-derive from `last_action`. Migrated 17 `_make_state(last_action=...)` calls to direct `user_intent=` / `pipeline_stage=` params. Migrated 6 `parsed["last_action"]` assertions: LOGGED/NO_MATCH → `parsed["pipeline_stage"]`; QUERY_DAILY_STATS/CHITCHAT/"" → `parsed["user_intent"]`. Renamed `test_empty_last_action` → `test_empty_user_intent`.
- Dropped `last_action` assertions across 7 writer test files (parallel new-field assertions added in the previous commit already cover the same surface).
- Dropped `last_action` state-setup entries from `test_feedback_integration.py` (5 sites), `test_calculate_macros_node.py`, `test_multi_item_loop.py`, and `test_log_yesterday_e2e.py`.
- Fixed a docstring `assert:` line in `test_calculate_macros_node.py` that referenced `last_action`.

### Docs

- Updated `docs/patterns/state-schemas.md` — dropped the `last_action` table row and the `GraphAction` bullet; cleaned the encapsulation paragraph; cleaned the field-list reference. The "Pre-refactor, both were stored in a single `last_action` field" historical sentence in the ADR-0005 callout stays — it's accurate history.
- Updated `docs/adr/0005-split-user-intent-from-pipeline-stage.md` — rewrote the Decision section's deprecation paragraph to describe the actual landed shape (back-compat removed); marked Alternative §C as "Reconsidered during PR #32 review and accepted"; dropped the "two fields to keep consistent" and "removal is a tracked task" lines from Consequences.
- Updated `docs/adr/DECISIONS.md` index one-liner.
- Added an Update callout at the top of `docs/plans/split-user-intent-from-pipeline-stage-review-guide.md` flagging that mentions of dual-write / legacy fallback describe the intermediate state, not the final diff.
- Added a postscript Update to the original commit log (`commit_logs/2026-05-11_22-43-48_split-user-intent-from-pipeline-stage.md`) pointing here.

## Validation

| Level | Command | Result |
|---|---|---|
| Lint | `uv run ruff check .` | ✅ All checks passed |
| Unit | `uv run pytest tests/unit/ -v` | ✅ 193 passing (was 197; deleted `TestGraphActionIntegrity` = 1 test + `TestLegacyCheckpointFallback` = 3 tests, net -4) |
| Integration | `uv run pytest tests/integration/ -v` | ✅ 56 passing |
| Graph-API E2E | `uv run pytest tests/graph_api/ -v -s` | ✅ 15 passing — including `TestQueryFoodInfoPath` (the silent-commit regression test is unaffected by this cleanup) |
| Hygiene | `grep -rn 'last_action\|GraphAction\|intent_from_legacy\|stage_from_legacy' src/ tests/` | ✅ zero non-historical results |

## What's next

- **`brain/TASKS.md` follow-up cleanup** — mark the "Remove `last_action` from `AgentState`" Maintenance entry as ✅ with this PR reference. (Separate repo; auto-committed by Obsidian Git plugin on its own cadence.)
- **No outstanding deprecation tail.** The only deferred work tracked by ADR-0005 is the `NO_MATCH` overload disambiguation (split `pipeline_stage="NO_MATCH"` into `SELECTION_NO_MATCH` vs `MACRO_CALCULATION_FAILED`).

## References

- Plan: `docs/plans/remove-last-action-deprecated-field.md` (34 ordered tasks; all executed)
- ADR: `docs/adr/0005-split-user-intent-from-pipeline-stage.md`
- Previous commit on branch: `a5c54c4 refactor(state): split last_action into user_intent + pipeline_stage; route QUERY_FOOD_INFO past commit`
- Original plan: `docs/plans/split-user-intent-from-pipeline-stage.md`
- Original review guide (with the Update callout): `docs/plans/split-user-intent-from-pipeline-stage-review-guide.md`
