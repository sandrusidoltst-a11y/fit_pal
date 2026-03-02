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

The `langgraph dev` server must be running before graph-api tests execute.
It is already available as a dev dependency (`langgraph-cli[inmem]`).

```bash
# Start server (keep running in a separate terminal)
uv run langgraph dev

# Verify it is up
curl http://localhost:2024/ok
```

The assistant name in `langgraph.json` must match the `assistant_id` used in tests.
Check `langgraph.json` for the graph name before writing tests.

---

## 2. Pytest Session Fixture (conftest.py in graph_api/)

Place this fixture in `tests/graph_api/conftest.py`:

```python
"""Shared fixtures for graph-api tests. Requires langgraph dev running on port 2024."""
import pytest
from langgraph_sdk import get_client


LANGGRAPH_DEV_URL = "http://localhost:2024"


@pytest.fixture(scope="session")
def lg_client():
    """
    Returns a langgraph-sdk client connected to the local dev server.
    Fails fast with a clear message if the server is not running.
    """
    import httpx
    try:
        httpx.get(f"{LANGGRAPH_DEV_URL}/ok", timeout=2).raise_for_status()
    except Exception:
        pytest.skip(
            "langgraph dev server not running. "
            "Start it with: uv run langgraph dev"
        )
    return get_client(url=LANGGRAPH_DEV_URL)


@pytest.fixture
async def thread(lg_client):
    """Creates a fresh thread for each test and yields its thread_id."""
    t = await lg_client.threads.create()
    yield t["thread_id"]
```

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

Prerequisites:
    langgraph dev server must be running: uv run langgraph dev
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


class TestQueryStatsPath:
    """Full path: input_parser → stats_lookup → response."""

    async def test_query_todays_stats_returns_response(self, lg_client, thread):
        """
        arrange: User message asking for today's nutritional stats.
        act:     Graph routes through stats_lookup to response.
        assert:  Run completes without error and final message is non-empty.
        """
        result = await lg_client.runs.wait(
            thread,
            ASSISTANT_ID,
            input={"messages": [{"role": "human", "content": "What did I eat today?"}]},
        )

        assert result is not None
        messages = result.get("messages", [])
        assert len(messages) >= 2
        assert messages[-1].get("content", "").strip() != ""


class TestChitchatPath:
    """Short path: input_parser → response (no food or stats query)."""

    async def test_greeting_routes_directly_to_response(self, lg_client, thread):
        """
        arrange: A plain greeting with no food or stats intent.
        act:     Graph routes directly to response node, skipping all food nodes.
        assert:  Run completes without error and final message is non-empty.
        """
        result = await lg_client.runs.wait(
            thread,
            ASSISTANT_ID,
            input={"messages": [{"role": "human", "content": "Hello, how are you?"}]},
        )

        assert result is not None
        messages = result.get("messages", [])
        assert len(messages) >= 2
        assert messages[-1].get("content", "").strip() != ""


class TestNoMatchPath:
    """Path where food_search returns no results: food_search → agent_selection(NO_MATCH) → response."""

    async def test_unknown_food_gracefully_handled(self, lg_client, thread):
        """
        arrange: User logs a food name that cannot exist in the database.
        act:     Graph routes to agent_selection which returns NO_MATCH, then response.
        assert:  Run completes without error; agent responds gracefully.
        """
        result = await lg_client.runs.wait(
            thread,
            ASSISTANT_ID,
            input={"messages": [{"role": "human", "content": "I ate 200g of xyzfood99999abcde"}]},
        )

        assert result is not None
        messages = result.get("messages", [])
        assert len(messages) >= 2
        assert messages[-1].get("content", "").strip() != ""


class TestMultiItemPath:
    """Multi-item loop: input_parser extracts 2+ items, graph loops through food_search for each."""

    async def test_multi_item_input_completes_without_error(self, lg_client, thread):
        """
        arrange: User logs two food items in a single message (triggers the loop).
        act:     Graph processes each item sequentially via food_search → calculate_log loop.
        assert:  Run completes without error; final message is non-empty.
        """
        result = await lg_client.runs.wait(
            thread,
            ASSISTANT_ID,
            input={"messages": [{"role": "human", "content": "I had 150g of chicken and 100g of rice"}]},
        )

        assert result is not None
        messages = result.get("messages", [])
        assert len(messages) >= 2
        assert messages[-1].get("content", "").strip() != ""
```

---

## 6. Keeping Graph-API Tests Durable

- **Assert on structure, not exact content.** LLM responses are non-deterministic. Assert that a response exists, is non-empty, and doesn't raise — not its exact wording.
- **One path per class.** Each `Test<Path>` class tests one routing branch. Adding a new graph edge = add a new test class.
- **Skip, don't fail, when server is down.** The `lg_client` fixture uses `pytest.skip` so the unit suite never fails due to a missing server.
- **Use a fresh thread per test.** The `thread` fixture is function-scoped so state never bleeds between tests.
- **Run deliberately.** Graph-api tests are slow (real LLM, real server). Never include them in the pre-commit gate. Run with `uv run pytest tests/graph_api/ -v -s`.
