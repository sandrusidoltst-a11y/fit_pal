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

    # Return update to state
    # We return the new values for the keys we want to update.
    # pending_food_items: model_dump() returns dicts matching List[PendingFoodItem]
    return {
        "pending_food_items": [item.model_dump() for item in result.items],
        "last_action": result.action.value,
        "processing_results": []
    }
