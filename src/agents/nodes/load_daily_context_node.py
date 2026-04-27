from datetime import datetime

import structlog
from langgraph.runtime import Runtime

from src.agents.state import AgentState
from src.config import USER_TIMEZONE
from src.context import ContextSchema
from src.services.daily_log_service import query_food_logs

logger = structlog.get_logger(__name__)


async def load_daily_context(state: AgentState, runtime: Runtime[ContextSchema]) -> dict:
    """Fetch today's food log into state via the query_food_logs tool.

    Runs immediately before response_node on every path. Always-fresh by
    construction — no consumer reads daily_log_today without the loader
    having just written it.

    See docs/adr/0003-daily-log-loader-before-response.md.
    """
    # Defensive fallback for graph invocations without context (Studio default,
    # some unit/integration tests). Mirrors response_node's same guard.
    context = runtime.context if runtime.context is not None else ContextSchema()
    user_id = context.user_id
    today_iso = datetime.now(USER_TIMEZONE).date().isoformat()
    logs = await query_food_logs.ainvoke({"target_date": today_iso, "user_id": user_id})
    logger.info("Loaded daily context", user_id=user_id, log_count=len(logs))
    return {"daily_log_today": logs}
