from typing import Literal, Optional

from pydantic import BaseModel, Field


class MacroEstimation(BaseModel):
    """Structured output for LLM macro estimation of off-menu foods."""

    calories: float = Field(
        ..., description="Estimated calories (kcal) for the given amount in grams"
    )
    protein: float = Field(
        ..., description="Estimated protein in grams for the given amount"
    )
    carbs: float = Field(
        ..., description="Estimated carbohydrates in grams for the given amount"
    )
    fat: float = Field(
        ..., description="Estimated fat in grams for the given amount"
    )
    name_en: str = Field(
        ..., description="English name of the food (translate if needed)"
    )
    name_he: str = Field(
        ..., description="Hebrew name of the food (translate if needed)"
    )
    category: Optional[
        Literal["protein", "carb", "fat", "free", "free_calories", "forbidden_main"]
    ] = Field(
        default=None,
        description="Coach-method category. Null if uncertain.",
    )
    tag: Optional[Literal["lean", "medium", "fatty"]] = Field(
        default=None,
        description="Optional protein tag. Null if not a protein or uncertain.",
    )
    default_unit: Optional[
        Literal["g", "piece", "slice", "scoop", "bottle", "cup", "tbsp", "tsp", "can"]
    ] = Field(
        default=None,
        description="The natural unit a user would say for this food (e.g., 'piece' for eggs).",
    )
    default_unit_weight_g: Optional[float] = Field(
        default=None,
        description="Grams per one natural unit (e.g., 50 for one egg).",
    )
