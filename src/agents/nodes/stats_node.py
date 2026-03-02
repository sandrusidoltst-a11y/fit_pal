from datetime import datetime, timezone
from typing import Dict

from src.agents.state import AgentState
from src.services.daily_log_service import query_food_logs


async def stats_lookup_node(state: AgentState) -> Dict:
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
        })
    else:
        # Default to consumed_at's date, or today
        target_date = consumed_at.date() if consumed_at else datetime.now(timezone.utc).date()
        report = await query_food_logs.ainvoke({"target_date": str(target_date)})

    return {"daily_log_report": report}
