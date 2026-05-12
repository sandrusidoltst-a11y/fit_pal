"""
Unit tests for checking consistency across state actions schemas.

Scope:
    Purely isolated unit tests exploring data typing definitions correctly representing node action definitions constraints.

LLM Usage:
    NONE — simple dictionary inspections only.
"""
from typing import get_args

from src.agents.state import GraphAction, PipelineStage, UserIntent
from src.schemas.input_schema import ActionType
from src.schemas.selection_schema import SelectionStatus


class TestGraphActionIntegrity:
    """Test functionality corresponding with static typing."""

    def test_graph_action_consistency(self):
        """
        arrange: read type representations across disparate enumerations statically.
        act:     parse definitions validating properties array values map accurately against constants.
        assert:  validates that internal typing dependencies match schema requirements without missing edge properties natively defined natively.
        """
        valid_actions = get_args(GraphAction)

        # Check that all ActionType values are in GraphAction
        for a in ActionType:
            assert a.value in valid_actions, f"Missing {a.value} from ActionType in GraphAction"

        # Check that all SelectionStatus values are in GraphAction
        for s in SelectionStatus:
            assert s.value in valid_actions, f"Missing {s.value} from SelectionStatus in GraphAction"

        # Check that "LOGGED" is in GraphAction
        assert "LOGGED" in valid_actions, "Missing 'LOGGED' in GraphAction"

        # Check HITL-specific actions
        for action in ("AWAITING_CONFIRMATION", "CONFIRMED", "REJECTED"):
            assert action in valid_actions, f"Missing '{action}' in GraphAction"


class TestUserIntentIntegrity:
    """UserIntent Literal must mirror ActionType exactly — no more, no less."""

    def test_user_intent_matches_action_type(self):
        """
        arrange: UserIntent Literal vs ActionType enum.
        act:     enumerate both.
        assert:  set equality — every ActionType value present, no extra values.
        """
        intent_values = set(get_args(UserIntent))
        action_type_values = {a.value for a in ActionType}
        assert intent_values == action_type_values, (
            f"UserIntent and ActionType drifted.\n"
            f"In UserIntent only: {intent_values - action_type_values}\n"
            f"In ActionType only: {action_type_values - intent_values}"
        )


class TestPipelineStageIntegrity:
    """PipelineStage Literal must cover all SelectionStatus values + HITL stages + LOGGED + PENDING."""

    def test_pipeline_stage_contains_selection_status(self):
        """SelectionStatus values are pipeline stages."""
        stage_values = set(get_args(PipelineStage))
        for s in SelectionStatus:
            assert s.value in stage_values, f"Missing {s.value} from SelectionStatus in PipelineStage"

    def test_pipeline_stage_contains_hitl_and_logged_and_pending(self):
        """HITL + commit stages must be present."""
        stage_values = set(get_args(PipelineStage))
        for stage in ("PENDING", "AWAITING_CONFIRMATION", "CONFIRMED", "REJECTED", "LOGGED"):
            assert stage in stage_values, f"Missing '{stage}' in PipelineStage"


class TestIntentStageDisjoint:
    """UserIntent and PipelineStage share no values — one is intent, the other is stage."""

    def test_user_intent_and_pipeline_stage_are_disjoint(self):
        """
        arrange: extract UserIntent and PipelineStage value sets.
        act:     intersect.
        assert:  intersection is empty.
        """
        intent_values = set(get_args(UserIntent))
        stage_values = set(get_args(PipelineStage))
        overlap = intent_values & stage_values
        assert not overlap, (
            f"UserIntent and PipelineStage must be disjoint, but share: {overlap}. "
            f"A value cannot be both an intent and a stage — see ADR-0005."
        )
