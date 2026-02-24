import json
import os
from datetime import date, datetime

from langchain_core.messages import SystemMessage

from src.agents.state import AgentState
from src.config import get_llm_for_node


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

    if last_action in ("LOGGED", "FAILED", "NO_MATCH", "SELECTED"):
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


def response_node(state: AgentState) -> dict:
    """Generate a natural, LLM-powered response based on current state.

    1. Loads the system prompt from prompts/response_generator.md.
    2. Builds a selective JSON context from the state.
    3. Prepends a SystemMessage (prompt + context) to the conversation history.
    4. Invokes the LLM and returns the AIMessage for state update.
    """
    # Load system prompt (mirrors selection_node.py pattern)
    prompt_path = os.path.join(os.getcwd(), "prompts", "response_generator.md")

    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()
    except FileNotFoundError:
        print(f"Warning: Prompt file not found at {prompt_path}")
        system_prompt = (
            "You are FitPal, a helpful fitness and nutrition coach. "
            "Respond based on the provided context."
        )

    # Build selective context JSON
    json_context = _build_context(state)

    # Construct system message with prompt + context
    system_message = SystemMessage(
        content=f"{system_prompt}\n\n---\nContext JSON:\n```json\n{json_context}\n```"
    )

    # Prepend system message to full conversation history
    messages = state.get("messages", [])
    full_messages = [system_message] + list(messages)

    # Invoke LLM
    llm = get_llm_for_node("response_node")
    result = llm.invoke(full_messages)

    return {"messages": [result]}
