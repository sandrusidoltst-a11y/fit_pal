import sys
import os
import json

# Add the src directory to the python path to ensure imports work correctly
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.agents.nutritionist import define_graph

def main():
    print("Initializing FitPal Agent to inspect memory...")
    try:
        app = define_graph()
    except Exception as e:
        print(f"Error initializing agent: {e}")
        sys.exit(1)
    
    # Define the thread we want to inspect
    config = {"configurable": {"thread_id": "terminal_user_1"}}
    
    # Retrieve the entire history of this thread (all checkpoints)
    # get_state_history returns an iterator, so we convert it to a list
    history = list(app.get_state_history(config))
    
    if not history:
        print("No history found for 'terminal_user_1'!")
        return

    print(f"\nFound {len(history)} checkpoint(s) for 'terminal_user_1'.")
    print("Printing from Oldest to Newest:\n" + "="*50)

    # Reverse the history so we see it chronologically (oldest first)
    for i, state_snapshot in enumerate(reversed(history)):
        print(f"\n--- Checkpoint {i + 1} ---")
        print(f"Checkpoint ID: {state_snapshot.config['configurable']['checkpoint_id']}")
        
        # Extract the actual Python dictionary from the state
        state_values = state_snapshot.values
        
        if not state_values:
            print("  State is completely empty.")
            continue

        # Extract only the key variables (ignoring full message objects to keep it clean)
        summary = {
            "last_action": state_values.get("last_action"),
            "selected_food_id": state_values.get("selected_food_id"),
            "current_date": str(state_values.get("current_date")),
            "pending_food_items_count": len(state_values.get("pending_food_items", [])),
            "pending_food_items": state_values.get("pending_food_items", []),
            "messages_count": len(state_values.get("messages", []))
        }
        
        # Print it as nicely formatted JSON
        print(json.dumps(summary, indent=2))
        
        # Optionally, print the very last message in this checkpoint
        if state_values.get("messages"):
            last_msg = state_values["messages"][-1]
            # Use the class name to know if it's HumanMessage or AIMessage
            msg_type = last_msg.__class__.__name__
            # Truncate content if it's too long for readability
            content = last_msg.content if isinstance(last_msg.content, str) else str(last_msg.content)
            display_content = content[:100] + "..." if len(content) > 100 else content
            print(f"  Last Message ({msg_type}): \"{display_content}\"")

if __name__ == "__main__":
    main()
