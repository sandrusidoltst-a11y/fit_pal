from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SelectionStatus(str, Enum):
    SELECTED = "SELECTED"  # Successfully selected a food item
    NO_MATCH = "NO_MATCH"  # No appropriate match found
    AMBIGUOUS = "AMBIGUOUS"  # Multiple valid matches, need clarification


class FoodSelectionResult(BaseModel):
    status: SelectionStatus = Field(..., description="Selection outcome")
    food_id: Optional[int] = Field(
        None, description="Selected food item ID (null if NO_MATCH or AMBIGUOUS)"
    )
    confidence: Optional[str] = Field(
        None, description="Reasoning for selection (for transparency)"
    )
