"""
Unit tests for checking consistency across state actions schemas.

Scope:
    Purely isolated unit tests exploring data typing definitions correctly representing node action definitions constraints.

LLM Usage:
    NONE — simple dictionary inspections only.
"""
from typing import get_args

from src.agents.state import GraphAction
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
