from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ItemEdit(BaseModel):
    """A single edit to apply to a batch item."""

    item_index: int = Field(
        ..., description="0-based index of the item in the batch to edit"
    )
    edit_type: Literal["change_amount", "remove"] = Field(
        ..., description="Type of edit"
    )
    new_count: Optional[float] = Field(
        None,
        description=(
            "New quantity in the unit specified by new_unit (only for change_amount). "
            "For grams, new_unit must be 'g'."
        ),
    )
    new_unit: Optional[
        Literal["g", "piece", "slice", "scoop", "bottle", "cup", "tbsp", "tsp", "can"]
    ] = Field(
        None,
        description=(
            "Unit for new_count (only for change_amount). 'g' for grams; "
            "natural units otherwise. If the user gave only a count without a unit, "
            "inherit from the item's original_unit shown in the batch context."
        ),
    )


class ConfirmationResponse(BaseModel):
    """Parsed user response to batch confirmation prompt."""

    action: Literal["confirm", "reject", "edit"] = Field(
        ...,
        description="User's intent: 'confirm' to approve all, 'reject' to cancel all, 'edit' to modify specific items",
    )
    edits: Optional[List[ItemEdit]] = Field(
        None,
        description="List of edits to apply (only when action is 'edit')",
    )
