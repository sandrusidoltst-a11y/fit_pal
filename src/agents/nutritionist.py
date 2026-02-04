from langgraph.graph import StateGraph, END
from src.agents.state import AgentState

def define_graph():
    # Initialize the graph with the AgentState
    workflow = StateGraph(AgentState)

    # placeholder node
    def start_node(state: AgentState):
        return {"messages": ["Agent initialized"]}

    workflow.add_node("start", start_node)
    workflow.set_entry_point("start")
    workflow.add_edge("start", END)

    return workflow.compile()
