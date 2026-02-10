from enum import Enum
from pydantic import BaseModel, Field
from datetime import date, time
from typing import List, Optional, Literal

class ActionType(str, Enum):
    LOG_FOOD = "LOG_FOOD"
    QUERY_FOOD_INFO = "QUERY_FOOD_INFO"
    QUERY_DAILY_STATS = "QUERY_DAILY_STATS"
    CHITCHAT = "CHITCHAT"

class SingleFoodItem(BaseModel):
    food_name: str = Field(..., description="Normalized name for DB lookup")
    amount: float = Field(..., description="Estimated weight of the food")
    unit: Literal["g"] = Field(default="g", description="Unit of measurement, strictly 'g'")
    original_text: str = Field(..., description="The original text description of the food item")

class FoodIntakeEvent(BaseModel):
    action: ActionType
    items: List[SingleFoodItem] = Field(default_factory=list)
    meal_type: Optional[str] = Field(None, description="Type of meal, e.g. Breakfast, Lunch, Dinner")
    date: Optional[date] = None
    time: Optional[time] = None
