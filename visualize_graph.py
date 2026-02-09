from src.agents.nutritionist import define_graph
import os

def visualize():
    print("Generating agent graph visualization...")
    app = define_graph()
    
    try:
        # Try to generate PNG using mermaid.ink or local tools
        # draw_mermaid_png() requires pygraphviz or similar, which might not be present.
        # So we also print the mermaid code as a fallback.
        mermaid_code = app.get_graph().draw_mermaid()
        print("\nMermaid Diagram Code (copy this to https://mermaid.live/):")
        print("-" * 40)
        print(mermaid_code)
        print("-" * 40)
        
        # Attempt to save PNG (might fail if dependencies are missing)
        try:
            png_data = app.get_graph().draw_mermaid_png()
            with open("agent_graph.png", "wb") as f:
                f.write(png_data)
            print("\nSuccess! Graph saved to 'agent_graph.png'")
        except Exception as e:
            print(f"\nNote: Could not save PNG directly ({e}).")
            print("You can use the Mermaid code above to see the graph online.")
            
    except Exception as e:
        print(f"Error generating visualization: {e}")

if __name__ == "__main__":
    visualize()
