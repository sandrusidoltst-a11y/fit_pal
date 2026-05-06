from datetime import datetime
from typing import Dict

from langgraph.runtime import Runtime

from src.agents.state import AgentState
from src.config import USER_TIMEZONE
from src.context import ContextSchema
from src.services.daily_log_service import query_food_logs


async def stats_lookup_node(state: AgentState, runtime: Runtime[ContextSchema]) -> Dict:
    """Retrieve nutritional logs based on the QUERY_DAILY_STATS sub-state.

    Branches on named fields (no field-presence-as-discriminator):
      - range: ``start_date`` and ``end_date`` both set → range query.
      - single day: ``target_date`` set → single-day query.
      - default: today (Israel-local).
    """
    query_stats = state.get("query_stats", {})
    target_date = query_stats.get("target_date")
    start_date_field = query_stats.get("start_date")
    end_date_field = query_stats.get("end_date")

    user_id = runtime.context.user_id

    if start_date_field and end_date_field:
        report = await query_food_logs.ainvoke({
            "target_date": str(start_date_field),
            "end_date": str(end_date_field),
            "user_id": user_id,
        })
    elif target_date:
        report = await query_food_logs.ainvoke(
            {"target_date": str(target_date), "user_id": user_id}
        )
    else:
        # Default to today, Israel-local — not naive UTC.
        today = datetime.now(USER_TIMEZONE).date()
        report = await query_food_logs.ainvoke(
            {"target_date": str(today), "user_id": user_id}
        )

    return {"query_logs": report}
