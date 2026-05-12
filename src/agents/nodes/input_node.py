import os
from datetime import datetime

import structlog
from langchain_core.messages import SystemMessage

from src.agents.state import AgentState, LogFoodSubState, QueryStatsSubState
from src.config import BASE_DIR, USER_TIMEZONE, get_llm_for_node
from src.schemas.input_schema import (
    ChitchatEvent,
    LogFoodEvent,
    LogPersonalStatsEvent,
    QueryFoodInfoEvent,
    QueryStatsEvent,
    UserIntentEvent,
)

logger = structlog.get_logger(__name__)

# Load prompt once at import time — no file I/O during graph execution
_PROMPT_PATH = os.path.join(BASE_DIR, "prompts", "input_parser.md")
try:
    with open(_PROMPT_PATH, "r", encoding="utf-8") as _f:
        _SYSTEM_PROMPT = _f.read()
except FileNotFoundError:
    logger.warning("Prompt file not found, using fallback", path=_PROMPT_PATH)
    _SYSTEM_PROMPT = "You are a helpful nutrition assistant. Parse food intake."


def _current_time_str(now: datetime | None = None) -> str:
    """Format current time for system-prompt injection, in the user's local timezone.

    Optional ``now`` is a testability hook — tests pass a fixed UTC datetime and
    assert the conversion to Israel local time.
    """
    if now is None:
        now = datetime.now(USER_TIMEZONE)
    return now.astimezone(USER_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")


async def input_parser_node(state: AgentState):
    """
    Node to parse user input into structured food intake data.
    """
    llm = get_llm_for_node("input_node")
    structured_llm = llm.with_structured_output(UserIntentEvent)

    # Get the last message from the user
    last_message = state["messages"][-1]

    # Prepend the system time to the prompt
    now_str = _current_time_str()
    system_prompt_with_time = f"The current system time is: {now_str}\n\n{_SYSTEM_PROMPT}"

    # Construct prompt
    messages = [
        SystemMessage(content=system_prompt_with_time),
        last_message
    ]

    # Invoke LLM — discriminated union wrapped in `event`; unwrap to variant.
    # `hasattr(..., "action")` distinguishes a bare variant (mocked in unit
    # tests) from the UserIntentEvent wrapper (returned by the real LLM).
    parsed = await structured_llm.ainvoke(messages)
    result = parsed if hasattr(parsed, "action") else parsed.event

    # Items only exist on LOG_FOOD / QUERY_FOOD_INFO variants.
    items_count = len(result.items) if hasattr(result, "items") else 0
    logger.info("Input parsed", action=result.action.value, items=items_count)

    # Action-isinstance routing — populate the matching sub-state, leave the
    # other empty. Always write both keys so cross-turn residue is impossible.
    items: list[dict] = []
    log_food: LogFoodSubState = {}
    query_stats: QueryStatsSubState = {}

    if isinstance(result, LogFoodEvent):
        items = [item.model_dump() for item in result.items]
        log_food = {"consumed_at": result.consumed_at, "meal_type": result.meal_type}
    elif isinstance(result, QueryStatsEvent):
        query_stats = {
            "target_date": result.target_date,
            "start_date": result.start_date,
            "end_date": result.end_date,
        }
    elif isinstance(result, QueryFoodInfoEvent):
        items = [item.model_dump() for item in result.items]
    elif isinstance(result, (LogPersonalStatsEvent, ChitchatEvent)):
        # Nothing to extract.
        pass

    return {
        "pending_food_items": items,
        "last_action": result.action.value,        # DEPRECATED — see ADR-0005
        "user_intent": result.action.value,        # set once per turn
        "pipeline_stage": "PENDING",               # reset at turn start
        "processing_results": [],
        # Turn-entry clears — these fields are turn-local but were previously
        # cleared only by their consumers, leaving residue when consumers
        # didn't run. Resetting here makes the turn-boundary explicit.
        "query_logs": [],
        "pending_confirmations": [],
        "search_results": [],
        "selected_food_id": None,
        "log_food": log_food,
        "query_stats": query_stats,
    }
