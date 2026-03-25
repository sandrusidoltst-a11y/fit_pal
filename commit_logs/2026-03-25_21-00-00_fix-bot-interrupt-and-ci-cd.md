# fix: Bot interrupt handling + CI/CD pipeline

**Date**: 2026-03-25
**Branch**: debug_bot → merged to main
**Commits**: `5185a47`, `2774a0d`, `a2b4cc5`

## Overview

Fixed a bug where the Telegram bot echoed the user's own message instead of the HITL confirmation prompt during interrupts. Added structured logging to the bot, set up CI (GitHub Actions) and CD (auto-deploy to Railway).

## Bug Fix: Bot Interrupt Handling (`bot/gateway.py`)

### Problem
When the LangGraph graph hit `interrupt()` at `confirmation_node`, the bot read `messages[-1]` from the run result — which was the user's original human message (the graph hadn't reached `response_node` yet). The user saw their own text echoed back instead of the food confirmation prompt.

### Root Cause
The bot's `_handle_authenticated_message` always extracted the last message from the run output. On interrupted runs, the output only contains messages accumulated before the interrupt — no AI response exists yet. The actual confirmation content lives in the interrupt value, not in messages.

### Invisible in Traces
This bug was invisible in LangSmith traces and checkpoint logs — the graph itself worked correctly. The interrupt value contained the right data. The problem was purely in the bot layer's response extraction.

### Fix
- Renamed `_check_interrupted()` → `_get_interrupt_state()` — now returns `(is_interrupted, formatted_text)` tuple
- Extracts interrupt value from `tasks[0].interrupts[0].value` via thread state endpoint
- Added `_format_interrupt_value()` — formats the confirmation dict (question, items, totals) into a readable Telegram message with bullet points and macro breakdown
- Response logic: if interrupted → send interrupt text; else → send last AI message

## Structured Logging (`bot/gateway.py`)

- Switched from `logging` to `structlog` (consistent with `src/` layer)
- Added content logging: user message in, bot response out (truncated to 500 chars)
- Added structured fields: `chat_id`, `thread_id`, `status_code` on errors
- Visible in Railway logs for debugging user-reported issues

## Lint Fixes (E402)

Reordered `logger = structlog.get_logger(__name__)` after all imports in 4 files:
- `src/agents/nodes/selection_node.py`
- `src/config.py`
- `src/services/daily_log_service.py`
- `src/tools/food_lookup.py`

## CI Pipeline (`.github/workflows/ci.yml`)

| Job | Trigger | What |
|---|---|---|
| Lint & Unit Tests | Every push/PR to `main` | `ruff check .` + `pytest tests/unit/` |
| Integration Tests | After lint passes | `pytest tests/integration/` (needs `SUPABASE_DB_URL` secret) |
| E2E Graph-API Tests | Manual trigger only | `pytest tests/graph_api/` (needs `SUPABASE_DB_URL` + `OPENAI_API_KEY`) |

## CD Pipeline (`.github/workflows/cd.yml`)

Triggers on every push to `main`:
1. Build both Docker images (`fitpal-bot` + `fitpal-server`)
2. Push to Docker Hub (`dolevsan/fitpal-bot:latest`, `dolevsan/fitpal-server:latest`)
3. Redeploy both services on Railway via CLI

### Required GitHub Secrets
| Secret | Purpose |
|---|---|
| `DOCKERHUB_USERNAME` | Docker Hub login |
| `DOCKERHUB_TOKEN` | Docker Hub access token |
| `RAILWAY_TOKEN` | Railway API token for redeploy |
| `SUPABASE_DB_URL` | Integration test DB connection |
| `OPENAI_API_KEY` | E2E tests (manual trigger only) |

## Test Updates (`tests/unit/test_gateway.py`)

- Updated 6 tests: `_check_interrupted` mock → `_get_interrupt_state` with `(bool, str | None)` return
- Updated `test_interrupt_detected_sets_flag`: now verifies interrupt text is sent to user (not echoed human message) and uses human message in mock result (reflecting real interrupted run output)

## Files Created
- `.github/workflows/ci.yml` — CI pipeline
- `.github/workflows/cd.yml` — CD pipeline

## Files Modified
- `bot/gateway.py` — interrupt fix, structlog, content logging
- `tests/unit/test_gateway.py` — updated mocks for new API
- `src/agents/nodes/selection_node.py` — logger reorder
- `src/config.py` — logger reorder
- `src/services/daily_log_service.py` — logger reorder
- `src/tools/food_lookup.py` — logger reorder
