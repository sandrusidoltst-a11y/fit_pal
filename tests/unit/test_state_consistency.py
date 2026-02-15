import pytest
from src.schemas.input_schema import ActionType
from src.schemas.selection_schema import SelectionStatus
from src.agents.state import GraphAction
from typing import get_args

def test_graph_action_consistency():
    valid_actions = get_args(GraphAction)
    
    # Check that all ActionType values are in GraphAction
    for a in ActionType:
        assert a.value in valid_actions, f"Missing {a.value} from ActionType in GraphAction"
        
    # Check that all SelectionStatus values are in GraphAction
    for s in SelectionStatus:
        assert s.value in valid_actions, f"Missing {s.value} from SelectionStatus in GraphAction"
        
    # Check that "LOGGED" is in GraphAction
    assert "LOGGED" in valid_actions, "Missing 'LOGGED' in GraphAction"
