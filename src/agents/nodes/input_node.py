import os
from datetime import datetime

import structlog
from langchain_core.messages import SystemMessage

from src.agents.state import AgentState
from src.config import BASE_DIR, get_llm_for_node
from src.schemas.input_schema import FoodIntakeEvent

logger = structlog.get_logger(__name__)

# Load prompt once at import time — no file I/O during graph execution
_PROMPT_PATH = os.path.join(BASE_DIR, "prompts", "input_parser.md")
try:
    with open(_PROMPT_PATH, "r", encoding="utf-8") as _f:
        _SYSTEM_PROMPT = _f.read()
except FileNotFoundError:
    logger.warning("Prompt file not found, using fallback", path=_PROMPT_PATH)
    _SYSTEM_PROMPT = "You are a helpful nutrition assistant. Parse food intake."


async def input_parser_node(state: AgentState):
    """
    Node to parse user input into structured food intake data.
    """
    llm = get_llm_for_node("input_node")
    structured_llm = llm.with_structured_output(FoodIntakeEvent)

    # Get the last message from the user
    last_message = state["messages"][-1]

    # Prepend the system time to the prompt
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    system_prompt_with_time = f"The current system time is: {now_str}\n\n{_SYSTEM_PROMPT}"

    # Construct prompt
    messages = [
        SystemMessage(content=system_prompt_with_time),
        last_message
    ]

    # Invoke LLM
    result = await structured_llm.ainvoke(messages)

    logger.info("Input parsed", action=result.action.value, items=len(result.items))

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
