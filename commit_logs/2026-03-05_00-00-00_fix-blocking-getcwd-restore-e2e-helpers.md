# Fix: Replace blocking os.getcwd() with BASE_DIR + Restore E2E test helpers

**Date**: 2026-03-05
**Branch**: HITL_and_off_menu
**Commit**: `4032337`

## Changes Implemented

### Bug Fix — os.getcwd() BlockingError (5 nodes)
- Replaced `os.getcwd()` with `BASE_DIR` from `src.config` in all 5 affected nodes:
  - `confirmation_node.py` — blocked all HITL paths (confirm/reject/edit)
  - `input_node.py`
  - `calculate_macros_node.py`
  - `response_node.py`
  - `selection_node.py`
- `BASE_DIR` is computed once at import time via `__file__` — deterministic and non-blocking
- RCA documented in `docs/rca/blocking-error-os-getcwd-in-async-nodes.md`

### E2E Test Infrastructure — Restored helpers
- `_run()` — wraps `runs.wait(raise_error=False)`, detects errors, saves server traceback to `.txt`
- `_extract_server_traceback()` — reads server log, extracts most recent traceback for a given error type
- `_dump_error_log()` — writes `.txt` file to `tests/graph_api/logs/`
- `_assert_interrupted()` — verifies graph paused at HITL interrupt
- Restored reject and edit flow test coverage (previously dropped)

## Validation
- **Unit tests**: 68/68 passed
- **E2E tests**: 7/8 passed (1 pre-existing IntegrityError on off-menu path — separate bug)
- **Ruff lint**: 1 pre-existing warning (unrelated unused import)

## Next Steps
- Fix `daily_logs.food_id` NOT NULL constraint to allow `None` for estimated (off-menu) items
- This is the root cause of the remaining E2E test failure (`TestNoMatchPath`)
