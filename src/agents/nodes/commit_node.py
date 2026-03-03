from datetime import datetime, timezone

from src.agents.state import AgentState
from src.services.daily_log_service import log_food_entry, query_food_logs


async def commit_node(state: AgentState) -> dict:
    """Write all confirmed food items to the database in batch.

    Only called after user confirms via confirmation_node.
    Reads items from pending_confirmations state field.
    """
    batch = state.get("pending_confirmations", [])

    if not batch:
        return {}

    # Prepare timestamp
    consumed_at = state.get("consumed_at")
    now = datetime.now(timezone.utc)

    if consumed_at:
        if consumed_at.tzinfo is None:
            timestamp = consumed_at.replace(tzinfo=timezone.utc)
        else:
            timestamp = consumed_at
    else:
        timestamp = now

    processing_results = list(state.get("processing_results", []))

    # Write each item to DB
    for item in batch:
        await log_food_entry.ainvoke(
            {
                "food_id": item.get("food_id"),
                "amount_g": item["amount_g"],
                "calories": item["calories"],
                "protein": item["protein"],
                "carbs": item["carbs"],
                "fat": item["fat"],
                "timestamp": timestamp.isoformat(),
                "original_text": item.get("original_text", ""),
            }
        )

        processing_results.append(
            {
                "food_name": item["food_name"],
                "amount": item["amount_g"],
                "unit": "g",
                "original_text": item.get("original_text", ""),
                "status": "LOGGED",
                "message": f"Logged {item['food_name']} ({item['calories']}kcal)",
                "source": item.get("source"),
            }
        )

    # Fetch updated daily report
    updated_report = []
    if consumed_at:
        updated_report = await query_food_logs.ainvoke(
            {"target_date": str(consumed_at.date())}
        )

    return {
        "pending_confirmations": [],
        "daily_log_report": updated_report
        if updated_report
        else state.get("daily_log_report", []),
        "last_action": "LOGGED",
        "processing_results": processing_results,
    }
