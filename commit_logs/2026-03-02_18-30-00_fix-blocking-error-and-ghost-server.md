# Fix: BlockingError in Async Nodes & Ghost Server Processes

**Commit:** `30ad995`
**Branch:** `Testing_improvements`
**Date:** 2026-03-02

## Changes

### BlockingError Fix (src + tests)
- **`calculate_log_node.py`**: Replaced sync `calculate_food_macros.invoke()` with async `session.get(FoodItem, id)` + pure `compute_food_macros()` helper.
- **`food_search_node.py`**: Converted from sync `search_food.invoke()` to direct async SQLAlchemy query. Node is now `async def`.
- **`food_lookup.py`**: Extracted `compute_food_macros()` pure function (no DB, no I/O). Existing `@tool` functions kept for LangChain compatibility.
- **Tests updated**: `test_calculate_log_node`, `test_feedback_logic`, `test_food_search_node`, `test_multi_item_loop` — all mock async DB sessions instead of tool invocations.
- **RCA doc**: `docs/rca/blocking-error-sync-tools-in-async-nodes.md`

### Ghost Server Fix (tests/graph_api/conftest.py)
- `taskkill /F /T /PID` — kills entire process tree, not just parent PID.
- `subprocess.DEVNULL` instead of `subprocess.PIPE` — prevents buffer deadlocks.
- Removed `CTRL_BREAK_EVENT` / `CREATE_NEW_PROCESS_GROUP` — unreliable on Windows.
- Increased startup timeout from 15s to 30s.

## Next Steps
- Push branch and open PR to merge into `main`.
- Consider adding a `conftest.py` integration test that verifies clean port release after teardown.
