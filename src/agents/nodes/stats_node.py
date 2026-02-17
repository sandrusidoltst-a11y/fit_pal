from typing import Dict

from src.agents.state import AgentState, QueriedLog
from src.database import get_db_session
from src.services import daily_log_service


def stats_lookup_node(state: AgentState) -> Dict:
    """Retrieve nutritional logs based on date context.

    If start_date and end_date are present, performs a range query.
    Otherwise, queries for the current_date.
    """
    start_date = state.get("start_date")
    end_date = state.get("end_date")
    current_date = state.get("current_date")

    with get_db_session() as session:
        if start_date and end_date:
            logs = daily_log_service.get_logs_by_date_range(
                session, start_date, end_date
            )
        else:
            # Default to current_date lookup
            logs = daily_log_service.get_logs_by_date(session, current_date)

        # Convert SQLAlchemy models to TypedDict for state
        report = []
        for log in logs:
            entry: QueriedLog = {
                "id": log.id,
                "food_id": log.food_id,
                "amount_g": log.amount_g,
                "calories": log.calories,
                "protein": log.protein,
                "carbs": log.carbs,
                "fat": log.fat,
                "timestamp": log.timestamp,
                "meal_type": log.meal_type,
                "original_text": log.original_text,
            }
            report.append(entry)

    return {"daily_log_report": report}
