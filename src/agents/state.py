from datetime import date, datetime
from typing import Annotated, List, Literal, Optional, TypedDict

from langgraph.graph.message import add_messages


class PendingFoodItem(TypedDict):
    """Single food item waiting to be processed.

    Mirrors the structure of SingleFoodItem Pydantic model
    from src/schemas/input_schema.py (converted via model_dump()).
    """

    food_name: str
    amount: float
    unit: str
    original_text: str


class SearchResult(TypedDict):
    """Result from food database search.

    Mirrors the return type of search_food tool
    from src/tools/food_lookup.py.
    """

    id: int
    name: str


from datetime import date, datetime

class QueriedLog(TypedDict):
    """Mirrors DailyLog model for reporting in state.
    
    Contains raw log data retrieved from the database.
    """
    id: int
    food_id: int
    amount_g: float
    calories: float
    protein: float
    carbs: float
    fat: float
    timestamp: datetime
    meal_type: Optional[str]
    original_text: Optional[str]

GraphAction = Literal[
    "LOG_FOOD",
    "QUERY_FOOD_INFO",
    "QUERY_DAILY_STATS",
    "CHITCHAT",
    "SELECTED",
    "NO_MATCH",
    "AMBIGUOUS",
    "LOGGED",
]

class ProcessingResult(PendingFoodItem):
    """Result of processing a single food item.

    Inherits all fields from PendingFoodItem (food_name, amount, unit, original_text)
    and adds status/message for user feedback.
    """

    status: Literal["LOGGED", "FAILED"]
    message: str


class AgentState(TypedDict):
    """State definition for the FitPal agent.

    Attributes:
        messages: List of messages in the conversation history.
        pending_food_items: Food items extracted from user input, pending processing.
        daily_log_report: List of raw logs queried from DB (replaces aggregated totals).
        current_date: The active date for logging or single-day query.
        start_date: Start date for range query context (inclusive).
        end_date: End date for range query context (inclusive).
        last_action: The last action type determined by input parser.
        search_results: Food search results for agent selection node.
        selected_food_id: Selected food ID from agent selection node.
        processing_results: Feedback results for multi-item processing.
    """

    messages: Annotated[List, add_messages]
    pending_food_items: List[PendingFoodItem]
    daily_log_report: List[QueriedLog]
    current_date: date
    start_date: Optional[date]
    end_date: Optional[date]
    last_action: GraphAction
    search_results: List[SearchResult]
    selected_food_id: Optional[int]
    processing_results: List["ProcessingResult"]


