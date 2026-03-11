from datetime import datetime, timezone
from typing import Dict

from langchain_core.runnables import RunnableConfig

from src.agents.state import AgentState
from src.services.daily_log_service import query_food_logs


async def stats_lookup_node(state: AgentState, config: RunnableConfig) -> Dict:
    """Retrieve nutritional logs based on date context.

    If start_date and end_date are present, performs a range query.
    Otherwise, queries for the current_date.
    """
    start_date = state.get("start_date")
    end_date = state.get("end_date")
    consumed_at = state.get("consumed_at")

    if start_date and end_date:
        report = await query_food_logs.ainvoke({
            "target_date": str(start_date),
            "end_date": str(end_date),
        }, config=config)
    else:
        # Default to consumed_at's date, or today
        target_date = consumed_at.date() if consumed_at else datetime.now(timezone.utc).date()
        report = await query_food_logs.ainvoke(
            {"target_date": str(target_date)}, config=config
        )

    return {"daily_log_report": report}
