import json
import os
from datetime import date, datetime

import structlog
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

from src.agents.state import AgentState
from src.config import BASE_DIR, get_llm_for_node
from src.context import ContextSchema

logger = structlog.get_logger(__name__)

# Load prompt once at import time — no file I/O during graph execution
_PROMPT_PATH = os.path.join(BASE_DIR, "prompts", "response_generator.md")
try:
    with open(_PROMPT_PATH, "r", encoding="utf-8") as _f:
        _SYSTEM_PROMPT = _f.read()
except FileNotFoundError:
    logger.warning("Response prompt file not found, using fallback", path=_PROMPT_PATH)
    _SYSTEM_PROMPT = (
        "You are FitPal, a helpful fitness and nutrition coach. "
        "Respond based on the provided context."
    )


def _serialize_date(obj):
    """JSON serializer for date/datetime objects."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def _build_context(state: AgentState) -> str:
    """Build a selective JSON context string based on last_action.

    Only includes state fields relevant to the current action
    to keep the LLM context window lean and focused.
    """
    last_action = state.get("last_action", "")
    context: dict = {"last_action": last_action}

    consumed_at = state.get("consumed_at")
    if consumed_at:
        context["consumed_at"] = (
            consumed_at.isoformat()
            if isinstance(consumed_at, datetime)
            else str(consumed_at)
        )

    if last_action in ("LOGGED", "FAILED", "NO_MATCH", "SELECTED", "CONFIRMED", "REJECTED"):
        # Food logging flow — include per-item processing results
        processing_results = state.get("processing_results", [])
        context["processing_results"] = processing_results

    elif last_action == "QUERY_DAILY_STATS":
        # Stats query flow — include raw daily log report
        daily_log_report = state.get("daily_log_report", [])
        context["daily_log_report"] = daily_log_report

        # Include date range if present
        start_date = state.get("start_date")
        end_date = state.get("end_date")
        if start_date:
            context["start_date"] = (
                start_date.isoformat()
                if isinstance(start_date, date)
                else str(start_date)
            )
        if end_date:
            context["end_date"] = (
                end_date.isoformat() if isinstance(end_date, date) else str(end_date)
            )

    # For CHITCHAT or other actions, context stays minimal (just last_action + consumed_at)

    return json.dumps(context, indent=2, default=_serialize_date)


async def response_node(state: AgentState, runtime: Runtime[ContextSchema]) -> dict:
    """Generate a natural, LLM-powered response based on current state.

    1. Uses the module-level system prompt from prompts/response_generator.md.
    2. Builds a selective JSON context from the state.
    3. Reads user profile from runtime context.
    4. Prepends a SystemMessage (prompt + profile + context) to the conversation history.
    5. Invokes the LLM and returns the AIMessage for state update.
    """
    # Build user profile section from runtime context
    from src.context import DEFAULT_DEV_PROFILE
    context = runtime.context if runtime.context is not None else ContextSchema()
    profile = context.user_profile if context.user_profile else DEFAULT_DEV_PROFILE

    # Current time (injected at call time, not import time)
    now_str = datetime.now().strftime("%A, %Y-%m-%d %H:%M")

    # Nutrition plan section
    plan = profile.get("nutrition_plan")
    plan_section = (
        f"\n\n## User Nutrition Plan\n{plan}"
        if plan
        else "\n\n## User Nutrition Plan\nNo plan set for this user yet."
    )

    # Build selective context JSON
    json_context = _build_context(state)

    # Construct system message with time + prompt + profile + plan + context
    system_message = SystemMessage(
        content=(
            f"Current time: {now_str}\n\n"
            f"{_SYSTEM_PROMPT}"
            f"\n\n---\n## User Profile\n"
            f"- Name: {profile.get('name', 'Unknown')}\n"
            f"- Age: {profile.get('age', 'Unknown')}\n"
            f"- Gender: {profile.get('gender', 'Unknown')}\n"
            f"- Height: {profile.get('height_cm', 'Unknown')}cm"
            f"{plan_section}"
            f"\n\n---\nContext JSON:\n```json\n{json_context}\n```"
        )
    )

    # Prepend system message to full conversation history
    messages = state.get("messages", [])
    full_messages = [system_message] + list(messages)

    # Invoke LLM
    llm = get_llm_for_node("response_node")
    result = await llm.ainvoke(full_messages)

    return {"messages": [result]}
