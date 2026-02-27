import os

from langchain_core.messages import HumanMessage, SystemMessage
from src.config import get_llm_for_node

from src.agents.state import AgentState
from src.schemas.selection_schema import FoodSelectionResult, SelectionStatus


def agent_selection_node(state: AgentState) -> dict:
    """
    Intelligently select the best food item from search results.
    If no matches are found, asks the LLM to provide estimated macros.
    """
    search_results = state.get("search_results", [])
    pending_items = state.get("pending_food_items", [])
    current_item = pending_items[0] if pending_items else {}

    # Edge case: Single result - auto-select
    if len(search_results) == 1:
        return {
            "selected_food_id": search_results[0]["id"],
            "last_action": "SELECTED",
        }

    # Multiple results (or 0 results for estimation) - use LLM selection
    prompt_path = os.path.join(os.getcwd(), "prompts", "agent_selection.md")

    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()
    except FileNotFoundError:
        print(f"Warning: Prompt file not found at {prompt_path}")
        system_prompt = "Select the most appropriate food item from the search results."

    llm = get_llm_for_node("selection_node")
    structured_llm = llm.with_structured_output(FoodSelectionResult)

    # Construct context for LLM
    user_context = f"User input: {pending_items[0]['original_text'] if pending_items else 'Unknown'}, Weight context: {pending_items[0].get('amount', 0)} {pending_items[0].get('unit', 'g')} if known."
    if not search_results:
        search_context = "Search results: [] (Empty. Must estimate macros per 100g)"
    else:
        search_context = "Search results:\n" + "\n".join(
            [f"- ID {r['id']}: {r['name']}" for r in search_results]
        )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"{user_context}\n\n{search_context}"),
    ]

    result = structured_llm.invoke(messages)

    processing_results = state.get("processing_results", [])

    if result.status == SelectionStatus.ESTIMATED:
        # User will be asked to confirm, store the estimation in state
        return {
            "selected_food_id": None,
            "last_action": "ESTIMATED",
            "current_estimation": {
                "calories": result.estimated_calories or 0,
                "protein": result.estimated_protein or 0,
                "carbs": result.estimated_carbs or 0,
                "fat": result.estimated_fat or 0,
            }
        }

    # Validate LLM response consistency
    if result.status == SelectionStatus.SELECTED and result.food_id is None:
        print("Warning: LLM returned SELECTED without food_id, treating as NO_MATCH")
        fail_item = {
            **current_item,
            "status": "FAILED",
            "message": f"Could not select match for {current_item.get('food_name')}"
        }
        return {
            "selected_food_id": None,
            "last_action": "NO_MATCH",
            "processing_results": processing_results + [fail_item]
        }

    if result.status == SelectionStatus.AMBIGUOUS:
        print("Warning: LLM returned AMBIGUOUS (not supported in MVP), treating as NO_MATCH")
        fail_item = {
            **current_item,
            "status": "FAILED",
            "message": f"Ambiguous match for {current_item.get('food_name')}"
        }
        return {
            "selected_food_id": None,
            "last_action": "NO_MATCH",
            "processing_results": processing_results + [fail_item]
        }
        
    if result.status == SelectionStatus.NO_MATCH:
         fail_item = {
             **current_item,
             "status": "FAILED",
             "message": f"No appropriate match found for {current_item.get('food_name')}"
         }
         return {
             "selected_food_id": None,
             "last_action": "NO_MATCH",
             "processing_results": processing_results + [fail_item]
         }

    return {
        "selected_food_id": result.food_id,
        "last_action": result.status.value,
    }
