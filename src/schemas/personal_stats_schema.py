"""Schema for personal stats extraction from natural language."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class PersonalStatExtraction(BaseModel):
    """Extracted personal stat from user message."""

    stat_type: Literal["weight", "body_fat"] = Field(
        ...,
        description="The type of body measurement. 'weight' for body weight, 'body_fat' for body fat percentage.",
    )
    value: float = Field(
        ...,
        description="The numeric value of the measurement. For weight: kilograms. For body fat: percentage (0-100).",
    )
    unit: Optional[str] = Field(
        None,
        description="The unit provided by the user, e.g. 'kg', 'lbs', '%'. Used for conversion if needed.",
    )
