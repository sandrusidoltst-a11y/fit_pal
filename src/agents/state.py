from datetime import date, datetime
from typing import Annotated, List, Literal, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class PendingFoodItem(TypedDict):
    """Single food item waiting to be processed.

    Mirrors the structure of SingleFoodItem Pydantic model
    from src/schemas/input_schema.py (converted via model_dump()).
    """

    food_name: str
    count: float
    unit: str
    original_text: str


class SearchResult(TypedDict):
    """Result from food database search.

    Mirrors the partial return type of search_food tool
    from src/services/food_service.py — minimal fields used by
    selection_node. calculate_macros_node fetches full row + mapping
    via get_food_by_id when needed.
    """

    id: str
    name_en: str
    name_he: Optional[str]
    source: str
    category: Optional[str]
    tag: Optional[str]


class QueriedLog(TypedDict):
    """Mirrors DailyLog model for reporting in state.

    Contains raw log data retrieved from the database.
    """

    id: str
    food_id: Optional[str]
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
    "AWAITING_CONFIRMATION",
    "CONFIRMED",
    "REJECTED",
    "LOG_PERSONAL_STATS",
]


class ProcessingResult(PendingFoodItem):
    """Result of processing a single food item.

    Inherits all fields from PendingFoodItem (food_name, count, unit, original_text)
    and adds status/message for user feedback. ``name_he`` is carried through
    so response_node can address the user in Hebrew.
    """

    status: Literal["LOGGED", "FAILED"]
    message: str
    source: Optional[Literal["database", "estimated"]]
    name_he: Optional[str]


class MacroResult(TypedDict):
    """Calculated macros for a single food item, pending user confirmation.

    Used by calculate_macros_node to accumulate batch previews
    before presenting to user for HITL confirmation.
    """

    name_en: str
    name_he: Optional[str]
    amount_g: float
    calories: float
    protein: float
    carbs: float
    fat: float
    source: Literal["database", "estimated"]
    category: Optional[str]
    tag: Optional[str]
    serving_amount_g: Optional[float]
    servings: Optional[float]
    default_unit: Optional[str]
    default_unit_weight_g: Optional[float]
    original_text: str
    food_id: Optional[str]


class InputState(TypedDict):
    """Public input schema for the FitPal graph.

    Used by LangSmith Studio and external callers to define the graph's
    public API. Only exposes the 'messages' field so LangSmith Studio
    renders a standard chat interface instead of a full state form.
    LangGraph automatically merges this into the full AgentState.
    """

    messages: Annotated[List[AnyMessage], add_messages]


class OutputState(TypedDict):
    """Public output schema for the FitPal graph.

    Defines what the graph exposes to external callers when the run
    completes. Mirrors InputState so the caller receives the updated
    conversation history (with the final AIMessage appended).
    """

    messages: Annotated[List[AnyMessage], add_messages]


class AgentState(TypedDict):
    """Full internal state definition for the FitPal agent.

    This schema is the single source of truth for all nodes inside the
    graph. It is a superset of InputState and OutputState.

    Attributes:
        messages: Conversation history (HumanMessages + AIMessages).
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

    messages: Annotated[List[AnyMessage], add_messages]
    pending_food_items: List[PendingFoodItem]
    daily_log_report: List[QueriedLog]
    consumed_at: Optional[datetime]
    start_date: Optional[date]
    end_date: Optional[date]
    last_action: GraphAction
    search_results: List[SearchResult]
    selected_food_id: Optional[str]
    processing_results: List["ProcessingResult"]
    pending_confirmations: List["MacroResult"]
