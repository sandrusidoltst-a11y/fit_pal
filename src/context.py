"""Context schema for LangGraph Runtime.

Defines the typed context passed to every graph run via the `context` field.
Available in nodes via `runtime: Runtime[ContextSchema]` and in tools via
`runtime: ToolRuntime[ContextSchema]`.
"""

import uuid
from dataclasses import dataclass, field
from typing import TypedDict


# Fallbacks for LangGraph Studio (no bot to inject context)
DEFAULT_DEV_USER_ID = "fbeeb45f-d728-4c7c-9e6d-7b9b41685da7"
DEFAULT_DEV_PROFILE: dict = {
    "name": "Dev User",
    "height_cm": 175.0,
    "age": 25,
    "gender": "male",
}


class UserProfile(TypedDict, total=False):
    """User profile data collected during onboarding."""

    name: str
    height_cm: float
    age: int
    gender: str


@dataclass
class ContextSchema:
    """Static context passed to every graph run.

    Injected by the bot gateway at invocation time.
    Available in nodes via runtime.context and in tools via runtime.context.
    """

    user_id: str = DEFAULT_DEV_USER_ID
    user_profile: dict = field(default_factory=lambda: DEFAULT_DEV_PROFILE.copy())

    def __post_init__(self):
        """Validate user_id is a valid UUID, fall back to default if not."""
        try:
            uuid.UUID(self.user_id)
        except (ValueError, AttributeError):
            self.user_id = DEFAULT_DEV_USER_ID
