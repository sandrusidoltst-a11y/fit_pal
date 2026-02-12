from datetime import date
from typing import Annotated, List, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    State definition for the FitPal agent.

    Attributes:
        messages: List of messages in the conversation history.
        pending_food_items: Food items extracted from user input, pending processing.
        daily_totals: Aggregated nutritional totals from DB {calories, protein, carbs, fat}.
        current_date: The date being tracked (for multi-day conversations).
        last_action: The last action type determined by input parser.
        search_results: Food search results for agent selection node.
    """

    messages: Annotated[List, add_messages]
    pending_food_items: List[dict]
    daily_totals: dict
    current_date: date
    last_action: str
    search_results: List[dict]
