# Rewrite E2E Tests with HTTP-Based BlockingError Detection

**Date**: 2026-03-04
**Commit**: `e6bcaad`
**Branch**: `HITL_and_off_menu`

## Changes Implemented

### test_graph_flows.py — Full Rewrite
- **`_run()` helper**: Wraps `runs.wait(raise_error=False)` to detect BlockingError from error type field. On failure, extracts server traceback from `server.log` and saves as `.txt` file.
- **`_assert_interrupted()` helper**: Verifies graph is paused at HITL interrupt via `threads.get_state()` tasks field.
- **10 tests across 5 classes**: NonInterruptPaths (chitchat, stats), FoodLoggingConfirm (DB item, off-menu, multi-item), FoodLoggingReject, FoodLoggingEdit (3-turn), ConversationMemory.

### conftest.py — Server Log Capture
- Server stdout/stderr now redirected to `tests/graph_api/logs/server.log` (was DEVNULL)
- Exposes `_server_log_path` module-level variable for traceback extraction
- Removed `in_process_graph` fixture and `MemorySaver` import

### Documentation Updates
- `graph-api-testing.md` skill reference: rewritten with `_run()` helper docs, HITL pattern, error log structure, conftest import pitfall
- `CLAUDE.md`: added `logs/` directory to project structure
- `.gitignore`: added `tests/graph_api/logs/`

## Key Discoveries

1. **LangGraph server strips error messages** for non-whitelisted errors. BlockingError TYPE is preserved but message becomes generic. Full traceback only in server stderr.
2. **Pytest conftest module identity**: Pytest loads conftest as `graph_api.conftest`, not `tests.graph_api.conftest`. Using the wrong import creates a duplicate module where fixture-set globals are invisible.
3. **`os.getcwd()` in confirmation_node.py:115** is a sync call flagged by blockbuster — root cause of all food-logging test failures.

## Next Steps

- [ ] Fix the BlockingError in `confirmation_node.py:115` — replace `os.getcwd()` with `Path(__file__).parent` based path
- [ ] Re-run full E2E suite to verify all 10 tests pass
- [ ] Check for other `os.getcwd()` or similar sync calls across all nodes
