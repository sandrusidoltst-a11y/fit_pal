from datetime import date, datetime
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    LOG_FOOD = "LOG_FOOD"
    QUERY_FOOD_INFO = "QUERY_FOOD_INFO"
    QUERY_DAILY_STATS = "QUERY_DAILY_STATS"
    CHITCHAT = "CHITCHAT"


class SingleFoodItem(BaseModel):
    food_name: str = Field(..., description="Normalized name for DB lookup")
    amount: float = Field(..., description="Estimated weight of the food")
    unit: Literal["g"] = Field(
        default="g", description="Unit of measurement, strictly 'g'"
    )
    original_text: str = Field(
        ..., description="The original text description of the food item"
    )


class FoodIntakeEvent(BaseModel):
    action: ActionType
    items: List[SingleFoodItem] = Field(
        default_factory=list,
        description="List of food items. Only used for LOG_FOOD or QUERY_FOOD_INFO actions.",
    )
    meal_type: Optional[str] = Field(
        None, description="Type of meal, e.g. Breakfast, Lunch, Dinner"
    )
    target_date: Optional[date] = Field(
        None, description="Specific date for the query or log (e.g. yesterday, 2023-10-27)"
    )
    start_date: Optional[date] = Field(
        None, description="Start date for range queries (inclusive)"
    )
    end_date: Optional[date] = Field(
        None, description="End date for range queries (inclusive)"
    )
    timestamp: Optional[datetime] = Field(
        None, description="When the food was consumed (UTC) - DEPRECATED in favor of target_date"
    )
