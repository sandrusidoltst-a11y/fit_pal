"""
Unit tests compiling and validating full structural logic integrations.

Scope:
    Verify graph nodes and routing configurations function simultaneously to accurately
    build conversational flows under optimal states.

LLM Usage:
    MOCKED — no external integrations occur inside unit testing scopes.
"""
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.agents.nutritionist import define_graph


class TestFullFlowIntegration:
    """Class suite addressing complete execution chains within integration boundaries."""

    async def test_integration_full_flow(self):
        """
        arrange: build and load extensive MagicMock definitions simulating active logic blocks.
        act:     construct temporary Checkpointing memory to parse mock input text asynchronously.
        assert:  triggers system checks asserting exactly one resulting system context contains valid properties.
        """
        mock_llm = MagicMock()
        mock_ai_msg = AIMessage(content="Logged Apple Success")
        mock_llm.ainvoke = AsyncMock(return_value=mock_ai_msg)

        # Patch dependencies inside nutritionist.py context
        with patch("src.agents.nutritionist.input_parser_node") as mock_input, \
             patch("src.agents.nutritionist.food_search_node") as mock_search, \
             patch("src.agents.nutritionist.agent_selection_node") as mock_select, \
             patch("src.agents.nutritionist.calculate_macros_node") as mock_calc, \
             patch("src.agents.nutritionist.confirmation_node") as mock_confirm, \
             patch("src.agents.nutritionist.commit_node") as mock_commit, \
             patch("src.agents.nodes.response_node.get_llm_for_node") as mock_get_llm:

            mock_get_llm.return_value = mock_llm

            # 1. Input Parser returns initial state
            mock_input.return_value = {
                "pending_food_items": [
                    {"food_name": "Apple", "original_text": "apple", "amount": 1, "unit": "unit"}
                ],
                "last_action": "LOG_FOOD",
                "processing_results": []
            }

            # 2. Food Search returns results
            mock_search.return_value = {
                "search_results": [{"id": "food-uuid-1", "name": "Apple", "source": "database"}]
            }

            # 3. Selection returns choice
            mock_select.return_value = {
                "selected_food_id": "food-uuid-1",
                "last_action": "SELECTED"
            }

            # 4. Calculate macros returns preview (no DB write)
            mock_calc.return_value = {
                "pending_food_items": [],
                "pending_confirmations": [{
                    "food_name": "Apple",
                    "amount_g": 1,
                    "calories": 95,
                    "protein": 0.5,
                    "carbs": 25,
                    "fat": 0.3,
                    "source": "database",
                    "original_text": "apple",
                    "food_id": "food-uuid-1",
                }],
                "last_action": "AWAITING_CONFIRMATION",
                "selected_food_id": None,
            }

            # 5. Confirmation node returns Command to commit (bypass interrupt)
            mock_confirm.return_value = Command(
                goto="commit",
                update={
                    "pending_confirmations": [{
                        "food_name": "Apple",
                        "amount_g": 1,
                        "calories": 95,
                        "protein": 0.5,
                        "carbs": 25,
                        "fat": 0.3,
                        "source": "database",
                        "original_text": "apple",
                        "food_id": "food-uuid-1",
                    }],
                    "last_action": "CONFIRMED",
                }
            )

            # 6. Commit writes to DB and returns results
            mock_commit.return_value = {
                "pending_confirmations": [],
                "processing_results": [
                    {
                        "food_name": "Apple",
                        "status": "LOGGED",
                        "message": "Logged Apple (95kcal)",
                        "amount": 1,
                        "unit": "g",
                        "original_text": "apple",
                        "source": "database",
                    }
                ],
                "last_action": "LOGGED"
            }

            # Build the graph with an in-memory checkpointer for testing
            app = await define_graph(checkpointer=MemorySaver())

            # Invoke with user message
            final_state = await app.ainvoke(
                {"messages": [("user", "I ate an apple")]},
                config={"configurable": {"thread_id": "1"}}
            )

            # Verify response node output
            assert "messages" in final_state
            last_msg = final_state["messages"][-1]

            content = last_msg.content if hasattr(last_msg, "content") else last_msg["content"]
            assert content == "Logged Apple Success"

            # Verify the LLM was called with context containing processing_results
            call_args = mock_llm.ainvoke.call_args[0][0]
            system_content = call_args[0].content
            assert "processing_results" in system_content
