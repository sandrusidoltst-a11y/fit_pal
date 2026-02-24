import os
from datetime import datetime

from langchain_core.messages import SystemMessage

from src.agents.state import AgentState
from src.config import get_llm_for_node
from src.schemas.input_schema import FoodIntakeEvent

def input_parser_node(state: AgentState):
    """
    Node to parse user input into structured food intake data.
    """
    # Load system prompt
    prompt_path = os.path.join(os.getcwd(), "prompts", "input_parser.md")
    
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()
    except FileNotFoundError:
        # Fallback or error logging
        print(f"Warning: Prompt file not found at {prompt_path}")
        system_prompt = "You are a helpful nutrition assistant. Parse food intake."

    llm = get_llm_for_node("input_node")
    structured_llm = llm.with_structured_output(FoodIntakeEvent)

    # Get the last message from the user
    last_message = state["messages"][-1]
    
    # Prepend the system time to the system prompt
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    system_prompt_with_time = f"The current system time is: {now_str}\n\n{system_prompt}"

    # Construct prompt
    messages = [
        SystemMessage(content=system_prompt_with_time),
        last_message
    ]

    # Invoke LLM
    result = structured_llm.invoke(messages)

    # Prepare state updates
    updates = {
        "pending_food_items": [item.model_dump() for item in result.items],
        "last_action": result.action.value,
        "processing_results": [],
    }

    # Handle date logic
    if result.start_date and result.end_date:
        # Range query
        updates["start_date"] = result.start_date
        updates["end_date"] = result.end_date
        updates["consumed_at"] = None
    elif result.consumed_at:
        updates["consumed_at"] = result.consumed_at
        updates["start_date"] = None
        updates["end_date"] = None
    else:
        # Default to nothing
        updates["consumed_at"] = None
        updates["start_date"] = None
        updates["end_date"] = None

    return updates
