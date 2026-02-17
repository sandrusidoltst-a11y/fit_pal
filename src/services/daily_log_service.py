"""
Service layer for DailyLog CRUD operations.

Provides functions for creating, querying, and aggregating daily food log entries.
All functions accept an explicit SQLAlchemy Session for testability.
"""

from datetime import date, datetime
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models import DailyLog


def create_log_entry(
    session: Session,
    food_id: int,
    amount_g: float,
    calories: float,
    protein: float,
    carbs: float,
    fat: float,
    timestamp: datetime,
    meal_type: Optional[str] = None,
    original_text: Optional[str] = None,
) -> DailyLog:
    """
    Create and persist a new DailyLog entry.

    Args:
        session: Active database session.
        food_id: Foreign key to FoodItem.
        amount_g: Quantity consumed in grams.
        calories: Calculated calories for the amount.
        protein: Calculated protein (g) for the amount.
        carbs: Calculated carbs (g) for the amount.
        fat: Calculated fat (g) for the amount.
        timestamp: When the food was consumed (UTC).
        meal_type: Optional meal type (breakfast/lunch/dinner/snack).
        original_text: Optional original user input text.

    Returns:
        The created DailyLog instance with populated id and audit fields.
    """
    log = DailyLog(
        food_id=food_id,
        amount_g=amount_g,
        calories=calories,
        protein=protein,
        carbs=carbs,
        fat=fat,
        timestamp=timestamp,
        meal_type=meal_type,
        original_text=original_text,
    )
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


def get_daily_totals(session: Session, target_date: date) -> Dict[str, float]:
    """
    Aggregate nutritional totals for a specific date.

    Queries all DailyLog entries whose timestamp falls on target_date
    and returns summed macro values.

    Args:
        session: Active database session.
        target_date: The date to aggregate totals for.

    Returns:
        Dict with keys: calories, protein, carbs, fat (all floats, default 0.0).
    """
    stmt = select(
        func.coalesce(func.sum(DailyLog.calories), 0.0).label("calories"),
        func.coalesce(func.sum(DailyLog.protein), 0.0).label("protein"),
        func.coalesce(func.sum(DailyLog.carbs), 0.0).label("carbs"),
        func.coalesce(func.sum(DailyLog.fat), 0.0).label("fat"),
    ).where(func.date(DailyLog.timestamp) == target_date)

    result = session.execute(stmt).one()

    return {
        "calories": float(result.calories),
        "protein": float(result.protein),
        "carbs": float(result.carbs),
        "fat": float(result.fat),
    }


def get_logs_by_date(session: Session, target_date: date) -> List[DailyLog]:
    """
    Retrieve all log entries for a specific date.

    Args:
        session: Active database session.
        target_date: The date to query logs for.

    Returns:
        List of DailyLog objects for the given date, ordered by timestamp.
    """
    stmt = (
        select(DailyLog)
        .where(func.date(DailyLog.timestamp) == target_date)
        .order_by(DailyLog.timestamp)
    )
    return list(session.execute(stmt).scalars().all())


def get_logs_by_date_range(
    session: Session, start_date: date, end_date: date
) -> List[DailyLog]:
    """
    Retrieve all log entries within a date range (inclusive).

    Args:
        session: Active database session.
        start_date: Start of the range (inclusive).
        end_date: End of the range (inclusive).

    Returns:
        List of DailyLog objects within the range, ordered by timestamp.
    """
    stmt = (
        select(DailyLog)
        .where(func.date(DailyLog.timestamp) >= start_date)
        .where(func.date(DailyLog.timestamp) <= end_date)
        .order_by(DailyLog.timestamp)
    )
    return list(session.execute(stmt).scalars().all())
