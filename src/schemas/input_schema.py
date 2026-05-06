from datetime import date, datetime
from enum import Enum
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


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


class LogFoodEvent(BaseModel):
    action: Literal[ActionType.LOG_FOOD] = ActionType.LOG_FOOD
    items: List[SingleFoodItem] = Field(default_factory=list)
    meal_type: Optional[str] = Field(
        None, description="Type of meal, e.g. Breakfast, Lunch, Dinner"
    )
    consumed_at: Optional[datetime] = Field(
        None,
        description=(
            "When the food was eaten. Hierarchy: exact time provided -> use exact "
            "time; relative (e.g. '2 hours ago') -> parse from injected system "
            "time; specific date (e.g. 'yesterday') -> that date at 12:00:00; "
            "no time mentioned -> leave null."
        ),
    )


class QueryStatsEvent(BaseModel):
    action: Literal[ActionType.QUERY_DAILY_STATS] = ActionType.QUERY_DAILY_STATS
    target_date: Optional[date] = Field(
        None,
        description="Single day being asked about (e.g. 'yesterday'). Null = today.",
    )
    start_date: Optional[date] = Field(
        None, description="Start of date range (inclusive). Range queries only."
    )
    end_date: Optional[date] = Field(
        None, description="End of date range (inclusive). Range queries only."
    )

    @model_validator(mode="after")
    def _exactly_one_shape(self) -> "QueryStatsEvent":
        has_target = self.target_date is not None
        has_range = self.start_date is not None and self.end_date is not None
        if has_target and has_range:
            raise ValueError(
                "QueryStatsEvent: target_date is mutually exclusive with start_date+end_date"
            )
        return self


class QueryFoodInfoEvent(BaseModel):
    action: Literal[ActionType.QUERY_FOOD_INFO] = ActionType.QUERY_FOOD_INFO
    items: List[SingleFoodItem] = Field(default_factory=list)


class LogPersonalStatsEvent(BaseModel):
    action: Literal[ActionType.LOG_PERSONAL_STATS] = ActionType.LOG_PERSONAL_STATS


class ChitchatEvent(BaseModel):
    action: Literal[ActionType.CHITCHAT] = ActionType.CHITCHAT


_EventUnion = Union[
    LogFoodEvent,
    QueryStatsEvent,
    QueryFoodInfoEvent,
    LogPersonalStatsEvent,
    ChitchatEvent,
]


class FoodIntakeEvent(BaseModel):
    """Top-level wrapper for the per-action union.

    OpenAI's strict structured-output requires the top-level schema to be
    ``type: "object"``, so the union sits inside a single ``event`` field.
    Access the variant via ``result.event`` — each variant subclass exposes
    ``.action`` and only the fields valid for that action.

    The union is intentionally not annotated with ``Field(discriminator=...)``
    because that emits JSON Schema ``oneOf``, which OpenAI's strict mode
    rejects. Pydantic's default "smart" union mode still picks the correct
    variant at runtime via each variant's ``Literal[ActionType.<X>]`` action
    field, so per-action field isolation is preserved.
    """

    event: _EventUnion = Field(
        ..., description="Per-action variant; selected by `action` literal."
    )
