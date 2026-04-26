import structlog
from langgraph.runtime import Runtime

from src.agents.state import AgentState
from src.context import ContextSchema
from src.database import get_async_db_session
from src.services.daily_log_service import get_todays_logs_serialized

logger = structlog.get_logger(__name__)


async def load_daily_context(state: AgentState, runtime: Runtime[ContextSchema]) -> dict:
    """Fetch today's food log into state.

    Runs immediately before response_node on every path. Always-fresh by
    construction — no consumer reads daily_log_today without the loader
    having just written it.

    See docs/adr/0002-daily-log-loader-node-into-state.md.
    """
    # Defensive fallback for graph invocations without context (Studio default,
    # some unit/integration tests). Mirrors response_node's same guard.
    context = runtime.context if runtime.context is not None else ContextSchema()
    user_id = context.user_id
    async with get_async_db_session() as session:
        logs = await get_todays_logs_serialized(session, user_id)
    logger.info("Loaded daily context", user_id=user_id, log_count=len(logs))
    return {"daily_log_today": logs}
