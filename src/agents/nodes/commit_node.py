from datetime import datetime, timezone

import structlog
from langgraph.runtime import Runtime

from src.agents.state import AgentState
from src.context import ContextSchema
from src.services.daily_log_service import log_food_entry, query_food_logs
from src.services.food_service import create_food_item

logger = structlog.get_logger(__name__)


async def commit_node(state: AgentState, runtime: Runtime[ContextSchema]) -> dict:
    """Write all confirmed food items to the database in batch.

    Only called after user confirms via confirmation_node.
    Reads items from pending_confirmations state field.
    """
    batch = state.get("pending_confirmations", [])

    if not batch:
        logger.warning("Commit node called with empty batch")
        return {}

    logger.info("Committing confirmed batch", items=len(batch))

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
    user_id = runtime.context.user_id

    # Write each item to DB
    for item in batch:
        food_id = item.get("food_id")

        # Create FoodItem for estimated items before logging
        if item.get("source") == "estimated" and food_id is None and item["amount_g"] > 0:
            amount_g = item["amount_g"]
            created = await create_food_item.ainvoke(
                {
                    "name": item["food_name"],
                    "calories_per_100g": round((item["calories"] / amount_g) * 100, 2),
                    "protein_per_100g": round((item["protein"] / amount_g) * 100, 2),
                    "carbs_per_100g": round((item["carbs"] / amount_g) * 100, 2),
                    "fat_per_100g": round((item["fat"] / amount_g) * 100, 2),
                    "user_id": user_id,
                },
            )
            food_id = created["id"]

        await log_food_entry.ainvoke(
            {
                "food_id": food_id,
                "amount_g": item["amount_g"],
                "calories": item["calories"],
                "protein": item["protein"],
                "carbs": item["carbs"],
                "fat": item["fat"],
                "timestamp": timestamp.isoformat(),
                "original_text": item.get("original_text", ""),
                "user_id": user_id,
            },
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
            {"target_date": str(consumed_at.date()), "user_id": user_id},
        )

    return {
        "pending_confirmations": [],
        "daily_log_report": updated_report
        if updated_report
        else state.get("daily_log_report", []),
        "last_action": "LOGGED",
        "processing_results": processing_results,
    }
