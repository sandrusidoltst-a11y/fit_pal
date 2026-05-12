import json
import os
from collections import defaultdict
from datetime import date, datetime

import structlog
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

from src.agents.state import AgentState
from src.config import BASE_DIR, USER_TIMEZONE, get_llm_for_node
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


def _current_time_str(now: datetime | None = None) -> str:
    """Format current time for system-prompt injection, in the user's local timezone.

    Optional ``now`` is a testability hook — tests pass a fixed UTC datetime and
    assert the conversion to Israel local time.
    """
    if now is None:
        now = datetime.now(USER_TIMEZONE)
    return now.astimezone(USER_TIMEZONE).strftime("%A, %Y-%m-%d %H:%M")


def _format_daily_log(logs: list[dict]) -> str:
    """Render today's logs as a markdown section for the system prompt.

    Always emits a section (never silent): explicit "nothing logged yet today"
    is a useful signal for the empty-log coach-voice opener (audit Fix #5).
    Timestamps in each log dict are already Israel-local via _serialize_log.

    When logs carry coach-method metadata (``category``/``tag`` from the
    ``coach_food_mappings`` join), each line is annotated and a trailing
    "Today's Totals by Category" block gives the LLM pre-computed servings
    math so it doesn't have to sum grams in prose. Logs without a category
    still render in the per-line section but are excluded from the totals
    block (can't aggregate without a category).
    """
    if not logs:
        return "\n\n## Today's Log\nNothing logged yet today."
    lines = ["\n\n## Today's Log"]
    for log in logs:
        ts = log.get("timestamp") or ""
        amount = log.get("amount_g", 0)
        cals = log.get("calories", 0)
        protein = log.get("protein", 0)
        carbs = log.get("carbs", 0)
        fat = log.get("fat", 0)
        original = log.get("original_text") or ""
        label = original or f"{amount}g"
        category = log.get("category")
        tag = log.get("tag")
        annotation = ""
        if category:
            annotation = f" [{category},{tag}]" if tag else f" [{category}]"
        lines.append(
            f"- {ts} — {label} — "
            f"{cals:.0f} kcal, {protein:.1f}g protein, {carbs:.1f}g carbs, {fat:.1f}g fat"
            f"{annotation}"
        )

    totals_block = _format_totals_by_category(logs)
    if totals_block:
        lines.append(totals_block)
    return "\n".join(lines)


def _format_totals_by_category(logs: list[dict]) -> str:
    """Aggregate logs by coach-method category and render a totals block.

    Serving math uses the coach's method constants (not per-food
    ``serving_amount_g``):
    - protein: 20g protein = 1 protein serving
    - carb: 50g carbs = 1 carb serving
    - free_calories: 100 kcal = 1 unit of the free-calorie budget
    - free / forbidden_main / fat: no serving concept; raw grams + kcal only

    Returns an empty string when no log carries a category — keeps the legacy
    prompt shape for pre-Plan-3d (uncategorized) data and preserves existing
    test assertions that don't expect a totals block.
    """
    totals: dict[str, dict[str, float]] = defaultdict(
        lambda: {"amount_g": 0.0, "calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    )
    for log in logs:
        category = log.get("category")
        if not category:
            continue
        bucket = totals[category]
        bucket["amount_g"] += log.get("amount_g", 0) or 0
        bucket["calories"] += log.get("calories", 0) or 0
        bucket["protein"] += log.get("protein", 0) or 0
        bucket["carbs"] += log.get("carbs", 0) or 0
        bucket["fat"] += log.get("fat", 0) or 0

    if not totals:
        return ""

    lines = ["\n## Today's Totals by Category"]
    for category in sorted(totals.keys()):
        bucket = totals[category]
        if category == "protein":
            servings = round(bucket["protein"] / 20.0, 1)
            lines.append(
                f"- protein: {bucket['amount_g']:.0f}g total, "
                f"{bucket['protein']:.1f}g protein, {bucket['calories']:.0f} kcal "
                f"→ {servings} protein servings"
            )
        elif category == "carb":
            servings = round(bucket["carbs"] / 50.0, 1)
            lines.append(
                f"- carb: {bucket['amount_g']:.0f}g total, "
                f"{bucket['carbs']:.1f}g carbs, {bucket['calories']:.0f} kcal "
                f"→ {servings} carb servings"
            )
        elif category == "free_calories":
            units = round(bucket["calories"] / 100.0, 1)
            lines.append(
                f"- free_calories: {bucket['amount_g']:.0f}g total, "
                f"{bucket['calories']:.0f} kcal → {units} free-calorie units"
            )
        else:
            # free / forbidden_main / fat — no serving concept
            lines.append(
                f"- {category}: {bucket['amount_g']:.0f}g total, "
                f"{bucket['calories']:.0f} kcal"
            )
    return "\n".join(lines)


def _serialize_date(obj):
    """JSON serializer for date/datetime objects."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def _build_context(state: AgentState) -> str:
    """Build a selective JSON context string based on user_intent.

    Dispatches on ``user_intent`` (the user's original ask) rather than on
    ``last_action`` (which conflates intent with pipeline stage). Pre-refactor
    checkpoints that only have ``last_action`` set are handled via the legacy
    fallback. ``last_action`` is still emitted in the context for one release
    so the response prompt has a compatibility belt. See ADR-0005.
    """
    from src.agents.state import intent_from_legacy, stage_from_legacy

    intent = state.get("user_intent") or intent_from_legacy(state.get("last_action")) or ""
    stage = state.get("pipeline_stage") or stage_from_legacy(state.get("last_action")) or ""
    last_action = state.get("last_action", "")

    context: dict = {
        "user_intent": intent,
        "pipeline_stage": stage,
        "last_action": last_action,  # DEPRECATED — see ADR-0005
    }

    if intent in ("LOG_FOOD", "LOG_PERSONAL_STATS"):
        # Logging flow (food or body stats) — include per-item processing
        # results and the consumed_at the user gave (for "logged at..." phrasing).
        log_food = state.get("log_food", {})
        consumed_at = log_food.get("consumed_at")
        if consumed_at:
            context["consumed_at"] = (
                consumed_at.isoformat()
                if isinstance(consumed_at, datetime)
                else str(consumed_at)
            )
        context["processing_results"] = state.get("processing_results", [])

    elif intent == "QUERY_FOOD_INFO":
        # Nutrition Q&A — surface the DB-looked-up (or LLM-estimated) macros
        # so the LLM answers with grounded values, not a guess.
        queried = state.get("pending_confirmations", [])
        context["queried_foods"] = [
            {
                "name_en": item.get("name_en"),
                "name_he": item.get("name_he"),
                "amount_g": item.get("amount_g"),
                "calories": item.get("calories"),
                "protein": item.get("protein"),
                "carbs": item.get("carbs"),
                "fat": item.get("fat"),
                "source": item.get("source"),  # "database" or "estimated"
            }
            for item in queried
        ]

    elif intent == "QUERY_DAILY_STATS":
        # Stats query flow — include raw daily log report
        context["query_logs"] = state.get("query_logs", [])
        # Include the date hints the user gave (single day or range).
        query_stats = state.get("query_stats", {})
        target_date = query_stats.get("target_date")
        start_date = query_stats.get("start_date")
        end_date = query_stats.get("end_date")
        if target_date:
            context["target_date"] = (
                target_date.isoformat()
                if isinstance(target_date, date)
                else str(target_date)
            )
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

    # For CHITCHAT or unresolved intent, context stays minimal.

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
    now_str = _current_time_str()

    # Nutrition plan section
    plan = profile.get("nutrition_plan")
    plan_section = (
        f"\n\n## User Nutrition Plan\n{plan}"
        if plan
        else "\n\n## User Nutrition Plan\nNo plan set for this user yet."
    )

    # Today's log section — always rendered (empty state is a useful signal for the LLM).
    # Sourced from state, populated by load_daily_context (runs immediately before this node).
    # See docs/adr/0002-daily-log-loader-node-into-state.md.
    daily_log = state.get("daily_log_today", [])
    log_section = _format_daily_log(daily_log)

    # Build selective context JSON
    json_context = _build_context(state)

    # Construct system message with time + prompt + profile + plan + log + context
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
            f"{log_section}"
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
