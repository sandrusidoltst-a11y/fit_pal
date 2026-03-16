import os

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from src.config import BASE_DIR, get_llm_for_node

logger = structlog.get_logger(__name__)

from src.agents.state import AgentState
from src.schemas.selection_schema import FoodSelectionResult, SelectionStatus


def agent_selection_node(state: AgentState) -> dict:
    """
    Intelligently select the best food item from search results.

    Handles edge cases:
    - 0 results: Return NO_MATCH status
    - 1 result: Auto-select
    - N results: Use LLM to select best match
    """
    search_results = state.get("search_results", [])
    pending_items = state.get("pending_food_items", [])

    # Edge case: No search results — estimation handles NO_MATCH in calculate_macros
    if not search_results:
        return {
            "selected_food_id": None,
            "last_action": "NO_MATCH",
        }

    # Edge case: Single result - auto-select
    if len(search_results) == 1:
        return {
            "selected_food_id": search_results[0]["id"],
            "last_action": "SELECTED",
        }

    # Multiple results - use LLM selection
    prompt_path = os.path.join(BASE_DIR, "prompts", "agent_selection.md")

    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()
    except FileNotFoundError:
        logger.warning("Prompt file not found, using fallback", path=prompt_path)
        system_prompt = "Select the most appropriate food item from the search results."

    llm = get_llm_for_node("selection_node")
    structured_llm = llm.with_structured_output(FoodSelectionResult)

    # Construct context for LLM
    user_context = f"User input: {pending_items[0]['original_text'] if pending_items else 'Unknown'}"
    search_context = "Search results:\n" + "\n".join(
        [f"- ID {r['id']}: {r['name']}" for r in search_results]
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"{user_context}\n\n{search_context}"),
    ]

    result = structured_llm.invoke(messages)

    # Validate LLM response consistency
    if result.status == SelectionStatus.SELECTED and result.food_id is None:
        logger.warning("LLM returned SELECTED without food_id, treating as NO_MATCH")
        return {
            "selected_food_id": None,
            "last_action": "NO_MATCH",
        }

    if result.status == SelectionStatus.AMBIGUOUS:
        logger.warning("LLM returned AMBIGUOUS (not supported in MVP), treating as NO_MATCH")
        return {
            "selected_food_id": None,
            "last_action": "NO_MATCH",
        }

    return {
        "selected_food_id": result.food_id,
        "last_action": result.status.value,
    }
