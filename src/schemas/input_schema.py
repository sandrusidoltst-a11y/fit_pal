from datetime import date, datetime
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    LOG_FOOD = "LOG_FOOD"
    QUERY_FOOD_INFO = "QUERY_FOOD_INFO"
    QUERY_DAILY_STATS = "QUERY_DAILY_STATS"
    CHITCHAT = "CHITCHAT"
    LOG_PERSONAL_STATS = "LOG_PERSONAL_STATS"


class SingleFoodItem(BaseModel):
    food_name: str = Field(..., description="Normalized name for DB lookup")
    count: float = Field(
        ...,
        description="Numeric quantity in the given unit (e.g., 2 for '2 eggs', 200 for '200g chicken')",
    )
    unit: Literal[
        "g", "piece", "slice", "scoop", "bottle", "cup", "tbsp", "tsp", "can"
    ] = Field(
        default="g",
        description="Unit of measurement. 'g' for grams; natural units otherwise.",
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
    start_date: Optional[date] = Field(
        None, description="Start date for range queries (inclusive)"
    )
    end_date: Optional[date] = Field(
        None, description="End date for range queries (inclusive)"
    )
    consumed_at: Optional[datetime] = Field(
        None, description="The exact date and time the food was consumed. If only date is provided, use 12:00 PM of that date. Leave null if relative or exact time cannot be determined."
    )
