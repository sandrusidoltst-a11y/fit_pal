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
    new_amount_g: Optional[float] = Field(
        None, description="New amount in grams (only for change_amount)"
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
