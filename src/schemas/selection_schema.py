from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SelectionStatus(str, Enum):
    SELECTED = "SELECTED"  # Successfully selected a food item
    NO_MATCH = "NO_MATCH"  # No appropriate match found
    AMBIGUOUS = "AMBIGUOUS"  # Multiple valid matches, need clarification
    ESTIMATED = "ESTIMATED"  # Guessed macros using LLM


class FoodSelectionResult(BaseModel):
    status: SelectionStatus = Field(..., description="Selection outcome")
    food_id: Optional[int] = Field(
        None, description="Selected food item ID (null if NO_MATCH or AMBIGUOUS)"
    )
    confidence: Optional[str] = Field(
        None, description="Reasoning for selection (for transparency)"
    )
    estimated_calories: Optional[float] = Field(
        None, description="Estimated calories per 100g if status is ESTIMATED"
    )
    estimated_protein: Optional[float] = Field(
        None, description="Estimated protein per 100g if status is ESTIMATED"
    )
    estimated_carbs: Optional[float] = Field(
        None, description="Estimated carbs per 100g if status is ESTIMATED"
    )
    estimated_fat: Optional[float] = Field(
        None, description="Estimated fat per 100g if status is ESTIMATED"
    )
