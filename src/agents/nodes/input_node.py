from datetime import date
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from src.agents.state import AgentState
from src.schemas.input_schema import FoodIntakeEvent
import os

def get_parser_llm():
    return ChatOpenAI(model="gpt-4o", temperature=0)

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

    llm = get_parser_llm()
    structured_llm = llm.with_structured_output(FoodIntakeEvent)

    # Get the last message from the user
    last_message = state["messages"][-1]
    
    # Construct prompt
    messages = [
        SystemMessage(content=system_prompt),
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
        updates["current_date"] = result.end_date  # Default current to end of range or today?
        # clearer to set current_date to None or ignore it if range is set, 
        # but let's follow the plan: "clear current_date" implies it might be None or just ignored.
        # But AgentState definition says current_date: date (not Optional).
        # So I must provide a date. Let's use end_date or today.
        # The plan said: "(clear current_date)". But typeddict might complain if I set it to None if not Optional.
        # In state.py: current_date: date. It is NOT Optional.
        # So I should probably set it to something valid. 
        # However, for stats lookup, if start/end are present, strictly they are used.
        # Let's set current_date to date.today() as a fallback if not strict.
        updates["current_date"] = date.today() 
    elif result.target_date:
        # Specific date
        updates["current_date"] = result.target_date
        updates["start_date"] = None
        updates["end_date"] = None
    else:
        # Default to today
        updates["current_date"] = date.today()
        updates["start_date"] = None
        updates["end_date"] = None

    return updates
