"""
Graph-API tests for the FitPal nutritionist graph (nutritionist.py).

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

ASSISTANT_ID = "fitpal"  # Must match the graph name in langgraph.json


class TestFoodLoggingPath:
    """Full path: input_parser → food_search → agent_selection → calculate_log → response."""

    async def test_log_common_food_completes(self, lg_client, thread):
        """
        arrange: User message requesting to log a common food item found in the DB.
        act:     Graph runs to completion through the food-logging path.
        assert:  Run completes without error and the final message is non-empty.
        """
        result = await lg_client.runs.wait(
            thread,
            ASSISTANT_ID,
            input={"messages": [{"role": "human", "content": "I ate 200g of chicken"}]},
        )

        assert result is not None
        messages = result.get("messages", [])
        assert len(messages) >= 2  # HumanMessage + at least one AIMessage
        assert messages[-1]["content"].strip() != ""


class TestNoMatchPath:
    """Path: input_parser → food_search → agent_selection(NO_MATCH) → response."""

    async def test_unknown_food_completes_gracefully(self, lg_client, thread):
        """
        arrange: User logs a food name that cannot exist in the database.
        act:     Graph routes through agent_selection which returns NO_MATCH, then response.
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
        assert messages[-1]["content"].strip() != ""


class TestQueryStatsPath:
    """Full path: input_parser → stats_lookup → response."""

    async def test_query_todays_stats_completes(self, lg_client, thread):
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
        assert messages[-1]["content"].strip() != ""


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
        assert messages[-1]["content"].strip() != ""


class TestMultiItemPath:
    """Multi-item loop: input_parser extracts 2+ items, graph loops through food_search for each."""

    async def test_multi_item_input_completes(self, lg_client, thread):
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
        assert messages[-1]["content"].strip() != ""


class TestConversationMemory:
    """Verifies thread-bound state persistence across multiple runs."""

    async def test_memory_persists_across_turns(self, lg_client, thread):
        """
        arrange: First run introduces a name on the thread.
        act:     Second run asks for the name on the same thread.
        assert:  Full thread state shows both turns and agent recalls the name.
        """
        # Turn 1 — introduce a name
        run1 = await lg_client.runs.wait(
            thread,
            ASSISTANT_ID,
            input={"messages": [{"role": "human", "content": "Hi, my name is Bob"}]},
        )
        assert run1 is not None, "Run 1 returned None"
        run1_msgs = run1.get("messages", [])
        assert len(run1_msgs) >= 2, f"Run 1 produced {len(run1_msgs)} messages, expected >= 2"

        # Wait for thread to be idle before starting the second run
        thread_info = await lg_client.threads.get(thread)
        assert thread_info["status"] == "idle", f"Thread not idle after Run 1: {thread_info['status']}"

        # Turn 2 — ask for the name on the same thread
        run2 = await lg_client.runs.wait(
            thread,
            ASSISTANT_ID,
            input={"messages": [{"role": "human", "content": "What's my name?"}]},
        )
        assert run2 is not None, "Run 2 returned None — second run did not complete"
        run2_msgs = run2.get("messages", [])
        assert len(run2_msgs) >= 2, f"Run 2 produced {len(run2_msgs)} messages, expected >= 2"

        # Verify full accumulated thread state has both turns
        state = await lg_client.threads.get_state(thread)
        messages = state["values"]["messages"]
        assert len(messages) >= 4, f"Thread has {len(messages)} messages, expected >= 4 (2 turns)"
        assert "Bob" in messages[-1]["content"]
