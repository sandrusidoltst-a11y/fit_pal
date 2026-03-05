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
