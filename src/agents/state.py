from typing import TypedDict, Annotated, List
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    """
    State definition for the FitPal agent.
    
    Attributes:
        messages: List of messages in the conversation history.
        daily_calories: Total calories parsed for the current day.
        daily_protein: Total protein (g) for the current day.
        daily_carbs: Total carbs (g) for the current day.
        daily_fat: Total fat (g) for the current day.
    """
    messages: Annotated[List, add_messages]
    daily_calories: float
    daily_protein: float
    daily_carbs: float
    daily_fat: float
