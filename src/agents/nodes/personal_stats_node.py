"""Personal stats node — extracts and logs body measurements.

Uses LLM structured output to extract stat type and value from
natural language, then persists via the log_personal_stat tool.
"""

import os

import structlog
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

from src.agents.state import AgentState
from src.config import BASE_DIR, get_llm_for_node
from src.context import ContextSchema
from src.schemas.personal_stats_schema import PersonalStatExtraction
from src.services.personal_stats_service import log_personal_stat

logger = structlog.get_logger(__name__)

# Load prompt once at import time — no file I/O during graph execution
_PROMPT_PATH = os.path.join(BASE_DIR, "prompts", "personal_stats_extractor.md")
try:
    with open(_PROMPT_PATH, "r", encoding="utf-8") as _f:
        _SYSTEM_PROMPT = _f.read()
except FileNotFoundError:
    logger.warning("Personal stats prompt not found, using fallback", path=_PROMPT_PATH)
    _SYSTEM_PROMPT = "Extract the body measurement type and value from the user message."


async def personal_stats_node(state: AgentState, runtime: Runtime[ContextSchema]) -> dict:
    """Extract a body measurement from the user message and log it.

    1. Loads the extraction prompt.
    2. Uses structured output to get stat_type + value.
    3. Calls log_personal_stat tool.
    4. Returns processing_results for the response node.
    """
    messages = state.get("messages", [])
    last_message = messages[-1]

    # Extract stat via LLM
    llm = get_llm_for_node("personal_stats_node")
    structured_llm = llm.with_structured_output(PersonalStatExtraction)
    result = await structured_llm.ainvoke([
        SystemMessage(content=_SYSTEM_PROMPT),
        last_message,
    ])

    logger.info(
        "Personal stat extracted",
        stat_type=result.stat_type,
        value=result.value,
        unit=result.unit,
    )

    # Log stat via tool
    user_id = runtime.context.user_id
    await log_personal_stat.ainvoke(
        {"stat_type": result.stat_type, "value": result.value, "user_id": user_id},
    )

    # Build processing result for response node
    stat_label = "weight" if result.stat_type == "weight" else "body fat"
    unit = "kg" if result.stat_type == "weight" else "%"
    processing_results = list(state.get("processing_results", []))
    processing_results.append({
        "food_name": f"{stat_label}: {result.value}{unit}",
        "amount": result.value,
        "unit": unit,
        "original_text": last_message.content if hasattr(last_message, "content") else str(last_message),
        "status": "LOGGED",
        "message": f"Logged {stat_label}: {result.value}{unit}",
        "source": None,
    })

    return {
        "last_action": "LOGGED",
        "pipeline_stage": "LOGGED",
        "processing_results": processing_results,
    }
