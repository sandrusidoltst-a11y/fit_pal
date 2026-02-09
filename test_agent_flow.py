import os
import uuid
from src.config import get_openai_api_key
from src.agents.nutritionist import define_graph

# Ensure API Key is available
try:
    get_openai_api_key()
except ValueError as e:
    print(f"Error: {e}")
    exit(1)

def run_test():
    print("--- FitPal Agent Flow Test ---")
    
    # Initialize the graph
    app = define_graph()
    
    # Create a unique thread ID for this conversation
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    
    # Test cases
    test_inputs = [
        "I ate an apple (150g) and 2 eggs for breakfast",
        "How many calories did I eat today?",
        "Hi there, how are you?"
    ]
    
    for user_input in test_inputs:
        print(f"\n[USER]: {user_input}")
        
        # Prepare initial state
        initial_input = {"messages": [("user", user_input)]}
        
        # Run the agent (streaming events so we see the nodes)
        print("[AGENT STEPS]:")
        for event in app.stream(initial_input, config, stream_mode="updates"):
            for node_name, update in event.items():
                print(f"  -> {node_name}: {update}")
        
        # Get final state to see the summary
        final_state = app.get_state(config).values
        print(f"[FINAL ACTION]: {final_state.get('last_action')}")
        if final_state.get('pending_food_items'):
            print(f"[PENDING ITEMS]: {final_state.get('pending_food_items')}")

if __name__ == "__main__":
    run_test()
