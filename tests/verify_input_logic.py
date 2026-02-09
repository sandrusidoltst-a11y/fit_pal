import sys
import os
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

# Add project root to python path
sys.path.append(os.getcwd())
load_dotenv()

from src.agents.nodes.input_node import input_parser_node

def test_input_parser():
    print("Testing Input Parser Node...")
    
    # Test 1: Log Food
    print("\n--- Test 1: Log Food ---")
    state = {
        "messages": [HumanMessage(content="I had 200g of chicken breast and a cup of rice.")],
        "daily_totals": {}
    }
    
    result = input_parser_node(state)
    print(f"Result: {result}")
    
    items = result.get("pending_food_items", [])
    action = result.get("last_action")
    
    assert action == "LOG_FOOD", f"Expected LOG_FOOD, got {action}"
    # We expect roughly 2 items (Chicken, Rice). The parser might handle 'cup of rice' as 'Rice' with quantity '1 cup'
    print(f"Items found: {[i['food_name'] for i in items]}")
    
    assert len(items) >= 2, f"Expected at least 2 items, got {len(items)}"
    
    # Test 2: Chitchat
    print("\n--- Test 2: Chitchat ---")
    state = {
        "messages": [HumanMessage(content="Hello, how are you?")],
        "daily_totals": {}
    }
    result = input_parser_node(state)
    print(f"Result: {result}")
    assert result["last_action"] == "CHITCHAT", f"Expected CHITCHAT, got {result['last_action']}"

    print("\n[PASS] Verification Passed!")

if __name__ == "__main__":
    try:
        test_input_parser()
    except Exception as e:
        print(f"\n[FAIL] Verification Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
