import os
import sys
import pytest
from dotenv import load_dotenv

# Ensure project root is in python path
sys.path.append(os.getcwd())
load_dotenv()

@pytest.fixture
def basic_state():
    """Returns a basic AgentState structure for testing."""
    return {
        "messages": [],
        "daily_totals": {}
    }
