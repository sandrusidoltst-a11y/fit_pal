# Graph-API Testing — FitPal

Tests in `tests/graph_api/` run the full graph through the `langgraph dev` HTTP server
using the `langgraph-sdk` client. This is the same API surface LangSmith Studio uses —
it catches a class of bugs that unit tests and compile-only integration tests cannot.

**Bugs this tier catches that others don't:**
- Errors from `MemorySaver` or `AsyncSqliteSaver` that only surface at API runtime
- Routing failures that occur only on specific graph paths (e.g., a path not exercised in unit tests)
- State serialization issues across the checkpointer boundary
- Node errors that only surface when state is thread-bound and persisted

---

## 1. Prerequisites

The `langgraph dev` server is **auto-started** by the `conftest.py` session fixture.
No manual server startup is needed — just run the tests:

```bash
uv run pytest tests/graph_api/ -v -s
```

The conftest will:
1. Check if a server is already running on port 2024
2. If not, clean up any orphaned processes on that port
3. Start `uv run langgraph dev` as a subprocess
4. Wait up to 30s for the `/ok` healthcheck to pass
5. Tear down the server (with full process tree cleanup) when tests finish

The assistant name in `langgraph.json` must match the `assistant_id` used in tests.
Check `langgraph.json` for the graph name before writing tests.

---

## 2. Pytest Session Fixture (conftest.py in graph_api/)

The actual conftest provides these fixtures:

| Fixture | Scope | Purpose |
|---|---|---|
| `auto_start_langgraph_server` | session, autouse | Auto-starts server if not running; tears down on exit |
| `lg_client` | function | Returns a `langgraph-sdk` client connected to `http://127.0.0.1:2024` |
| `thread` | function | Creates a fresh thread per test and cleans it up after |

Key implementation details:
- Uses `subprocess.DEVNULL` (not `PIPE`) to prevent buffer deadlocks that create zombie processes
- On Windows, uses `taskkill /F /T /PID` to kill the entire process tree
- Registers `atexit` handler as a safety net for abnormal exits
- `lg_client` fails fast if the server goes down unexpectedly

---

## 3. Running a Graph Flow

Use `client.runs.wait()` for synchronous-style assertions in tests.
It blocks until the run completes and returns the final state.

```python
result = await lg_client.runs.wait(
    thread_id,
    assistant_id,           # graph name from langgraph.json, e.g. "nutritionist"
    input={"messages": [{"role": "human", "content": "I ate 100g of chicken"}]},
)
# result is a dict with the final OutputState values
messages = result["messages"]
last_message_content = messages[-1]["content"]
```

---

## 4. FitPal Path Matrix — Required Coverage

Every routing path through the graph must have at least one graph-api test.

| Test Class | Path | Representative Input |
|---|---|---|
| `TestFoodLoggingPath` | `input_parser → food_search → agent_selection → calculate_log → response` | `"I ate 100g of chicken breast"` |
| `TestQueryStatsPath` | `input_parser → stats_lookup → response` | `"What did I eat today?"` |
| `TestChitchatPath` | `input_parser → response` | `"Hello, how are you?"` |
| `TestNoMatchPath` | `input_parser → food_search → agent_selection(NO_MATCH) → response` | `"I ate xyzfood99999"` |
| `TestMultiItemPath` | `input_parser → food_search(loop x2) → ... → response` | `"I ate chicken and rice"` |

---

## 5. Full Test File Template

```python
"""
Graph-API tests for the FitPal nutritionist graph (`nutritionist.py`).

Scope:
    End-to-end flow tests running through the real langgraph dev server.
    Verifies that each routing path executes without runtime errors and
    produces a coherent final response.

LLM Usage:
    LIVE — all LLM calls are real. These tests make actual API calls.
    Categorized as graph-api tests; run deliberately, not in pre-commit gate.

Server:
    Auto-started by conftest.py session fixture. No manual startup needed.
"""
import pytest
from langgraph_sdk import get_client

ASSISTANT_ID = "nutritionist"  # Must match the graph name in langgraph.json


class TestFoodLoggingPath:
    """Full path: input_parser → food_search → agent_selection → calculate_log → response."""

    async def test_log_common_food_returns_response(self, lg_client, thread):
        """
        arrange: User message requesting to log a common food item found in the DB.
        act:     Graph runs to completion through the food-logging path.
        assert:  Run completes without error and the final message is non-empty.
        """
        result = await lg_client.runs.wait(
            thread,
            ASSISTANT_ID,
            input={"messages": [{"role": "human", "content": "I ate 100g of chicken breast"}]},
        )

        assert result is not None
        messages = result.get("messages", [])
        assert len(messages) >= 2  # HumanMessage + at least one AIMessage
        last = messages[-1]
        assert last.get("content", "").strip() != ""
```

---

## 6. Keeping Graph-API Tests Durable

- **Assert on structure, not exact content.** LLM responses are non-deterministic. Assert that a response exists, is non-empty, and doesn't raise — not its exact wording.
- **One path per class.** Each `Test<Path>` class tests one routing branch. Adding a new graph edge = add a new test class.
- **Server is auto-managed.** The conftest handles startup and teardown. Don't add manual server management to test files.
- **Use a fresh thread per test.** The `thread` fixture is function-scoped so state never bleeds between tests.
- **Run deliberately.** Graph-api tests are slow (real LLM, real server). Never include them in the pre-commit gate. Run with `uv run pytest tests/graph_api/ -v -s`.
