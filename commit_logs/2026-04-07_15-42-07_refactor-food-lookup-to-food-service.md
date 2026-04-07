# Refactor: `food_lookup` → `food_service` (Co-located Service + Tool Pattern)

**Commit**: `273acfd`
**Branch**: `Menu-and-Personal-Details`
**Date**: 2026-04-07

## Summary

Eliminated the architectural inconsistency between `src/tools/food_lookup.py` (standalone tools, no service layer) and the rest of the codebase. The food domain now follows the same **service + co-located `@tool` wrappers** template as `daily_log_service.py` and `personal_stats_service.py`.

`src/tools/` directory is gone. All DB-touching tools now live in `src/services/<domain>_service.py` next to their service functions.

## Why

- **Consistency**: 2 of 3 service files already used the dual-layer pattern. `food_lookup.py` was the odd one out.
- **Testability**: Service functions accept `session: AsyncSession`, enabling DI for tests and multi-step transactions.
- **Discoverability**: Open one file per domain, see services + tools + helpers in one place.
- **Unblocks `tool-first.md`**: The next pattern doc in the queue (`.claude/patterns/tool-first.md`) cannot describe a single coherent pattern while two contradictory patterns exist in code.

## Changes

### Created

- **`src/services/food_service.py`** — New canonical home for the food domain. Structure mirrors `daily_log_service.py` exactly:
  - Module docstring
  - Imports + logger
  - **Pure helpers**: `compute_food_macros(food, amount_g)`
  - **Service functions** (accept `session`):
    - `search_food_items(session, query, user_id) -> list[FoodItem]`
    - `get_food_by_id(session, food_id) -> FoodItem | None`
    - `create_food_item_record(session, ..., user_id, source) -> FoodItem`
  - Separator comment
  - **`@tool` wrappers** (own their session):
    - `search_food(query, user_id) -> list[dict]`
    - `calculate_food_macros(food_id, amount_g) -> dict`
    - `create_food_item(name, ..., source, user_id) -> dict`

### Modified

- `src/agents/nodes/food_search_node.py` — import `search_food` from `src.services.food_service`
- `src/agents/nodes/calculate_macros_node.py` — import `calculate_food_macros` from `src.services.food_service`
- `src/agents/nodes/confirmation_node.py` — import `calculate_food_macros` from `src.services.food_service`
- `src/agents/nodes/commit_node.py` — import `create_food_item` from `src.services.food_service`
- `src/agents/state.py` — `SearchResult` docstring path reference
- `CLAUDE.md` — project structure tree (added `food_service.py` under `services/` alphabetically, removed `src/tools/` block)
- `.claude/skills/test-engineering/references/integration-testing.md` — patch path example

### Renamed

- `tests/integration/test_food_lookup.py` → `tests/integration/test_food_service.py` (via `git mv`); module docstring, import, and `_patch_session` patch path all updated.

### Deleted

- `src/tools/food_lookup.py`
- `src/tools/` directory (was empty after deletion)

## Behavior Preservation (Non-Negotiable)

Zero behavior changes. Specifically preserved:

- **Two-tier search semantics**: shared `database` foods first; only fall back to user-scoped `estimated` foods if zero database matches. Not merged.
- **`calculate_food_macros` error contract**: returns `{"error": "..."}` on not-found, consumed by `calculate_macros_node.py:51`.
- **Tool names**: `search_food`, `calculate_food_macros`, `create_food_item` unchanged (would be a breaking change for any future LLM tool-calling binding).
- **Tool input schemas**: parameter names, defaults (`source="estimated"`, `user_id=""`), return shapes all unchanged.
- **`compute_food_macros`**: kept as a module-level pure helper (not nested) for testability and future direct-call flexibility.

## Validation

| Check | Result |
|---|---|
| `ruff check` on all changed files | All checks passed |
| Import smoke (food_service + 4 nodes) | OK |
| Graph compilation (`define_graph()`) | OK — 10 nodes |
| Stale-reference grep `src.tools.food_lookup` in `src/`, `tests/` | Zero matches |
| `uv run pytest tests/unit/ -v` | **95 passed** in 1.24s |
| `uv run pytest tests/integration/ -v` | **26 passed** in 60.90s — including all 4 renamed `test_food_service.py` tests |

## Files Changed

```
11 files changed, 827 insertions(+), 115 deletions(-)
 create  .agent/plans/refactor-food-lookup-to-service-pattern.md
 create  src/services/food_service.py
 delete  src/tools/food_lookup.py
 rename  tests/integration/{test_food_lookup.py => test_food_service.py} (92%)
 modify  .claude/skills/test-engineering/references/integration-testing.md
 modify  CLAUDE.md
 modify  src/agents/nodes/calculate_macros_node.py
 modify  src/agents/nodes/commit_node.py
 modify  src/agents/nodes/confirmation_node.py
 modify  src/agents/nodes/food_search_node.py
 modify  src/agents/state.py
```

## Next Steps

1. **Write `.claude/patterns/tool-first.md`** — the original blocker. The doc can now describe **one** coherent pattern: services + co-located `@tool` wrappers in `src/services/<domain>_service.py`.
2. Continue working through the remaining 7 pattern files in `.claude/patterns/`:
   - `llm-config.md`
   - `hitl-confirmation.md`
   - `off-menu-estimation.md`
   - `schema-management.md`
   - `auth-and-users.md`
   - `bot-gateway.md`
   - `data-flow.md`
3. **Optional follow-up**: add service-layer tests for `food_service` (calling `search_food_items(session, ...)` directly without `_patch_session`) — out of scope here but a natural next step now that the service layer exists.

## Notes

- The plan file (`.agent/plans/refactor-food-lookup-to-service-pattern.md`) is included in the commit as a permanent record of the refactor's design and rationale.
- `.vscode/` is intentionally not staged (local IDE config).
- This refactor was scoped intentionally narrow: structural-only, no opportunistic cleanup, no behavior changes.
