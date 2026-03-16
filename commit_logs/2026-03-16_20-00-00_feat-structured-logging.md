# feat: Add Structured Logging with structlog

**Date**: 2026-03-16
**Commit**: `7290a30`
**Branch**: `logging`

## Changes Implemented

Added production-level structured logging across the entire `src/` layer using `structlog`, which is the native logging library used by the LangGraph server.

### Files Modified (12)

| File | Log Points | Key Logs |
|---|---|---|
| `src/config.py` | 3 | DB backend, LLM provider/model, dev user fallback warning |
| `src/database.py` | 2 | Engine created, SSL verification disabled warning |
| `src/security/auth.py` | 6 | All auth failure paths, startup config warning, success debug |
| `src/agents/nodes/input_node.py` | 2 | Parsed action + item count, prompt fallback |
| `src/agents/nodes/food_search_node.py` | 1 | Empty queue warning |
| `src/tools/food_lookup.py` | 4 | Search hits/misses, food not found, food item creation |
| `src/agents/nodes/selection_node.py` | 3 | All 3 print() replaced (prompt fallback, LLM misbehavior) |
| `src/agents/nodes/calculate_macros_node.py` | 3 | Macro calc failure, estimation trigger, prompt fallback |
| `src/agents/nodes/confirmation_node.py` | 5 | User decisions (confirm/reject/edit), empty batch, prompt fallback |
| `src/agents/nodes/commit_node.py` | 2 | Batch commit start, empty batch warning |
| `src/services/daily_log_service.py` | 2 | Daily log created (INFO), query results (DEBUG) |
| `src/agents/nodes/response_node.py` | 1 | Prompt fallback |

### Design Decisions

- **structlog over stdlib logging**: LangGraph server uses structlog natively — our logs appear in the same structured format (timestamps, key-value pairs) without bridge formatting.
- **Keyword arguments**: `logger.info("event", key=value)` instead of `%s` formatting — enables JSON output via `LOG_JSON=true` for log aggregation tools.
- **Tool wrappers only**: Logging lives in `@tool` wrappers, not raw service functions, to avoid polluting test output.
- **Complement LangSmith**: Logs focus on infrastructure/auth/business signals, not LLM I/O (which LangSmith covers).

### Validation

- 83 unit tests passed (0 failures)
- Zero `print()` statements remain in non-script `src/` files
- Verified logs appear in `langgraph dev` server output

## Next Steps

- Step 7: Deploy LangGraph standalone server (Docker Compose on VPS)
- Consider adding `structlog` logging to `bot/gateway.py` and `bot/supabase_admin.py` for consistency (currently use stdlib `logging`)
