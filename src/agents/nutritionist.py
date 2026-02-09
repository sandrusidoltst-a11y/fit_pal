from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3
from src.agents.state import AgentState

from src.agents.nodes.input_node import input_parser_node

def define_graph():
    # Initialize the graph with the AgentState
    workflow = StateGraph(AgentState)

    # Placeholder nodes
    def food_lookup_node(state: AgentState):
        return {"messages": ["Searching for food..."]}

    def stats_lookup_node(state: AgentState):
        return {"messages": ["Calculating daily statistics..."]}

    def response_node(state: AgentState):
        return {"messages": ["Response placeholder"]}

    def route_parser(state: AgentState):
        action = state.get("last_action")
        if action in ["LOG_FOOD", "QUERY_FOOD_INFO"]:
            return "food_lookup"
        elif action == "QUERY_DAILY_STATS":
            return "stats_lookup"
        return "response"

    workflow.add_node("input_parser", input_parser_node)
    workflow.add_node("food_lookup", food_lookup_node)
    workflow.add_node("stats_lookup", stats_lookup_node)
    workflow.add_node("response", response_node)

    workflow.set_entry_point("input_parser")
    
    workflow.add_conditional_edges(
        "input_parser",
        route_parser,
        {
            "food_lookup": "food_lookup",
            "stats_lookup": "stats_lookup",
            "response": "response"
        }
    )
    
    workflow.add_edge("food_lookup", "response")
    workflow.add_edge("stats_lookup", "response")
    workflow.add_edge("response", END)

    conn = sqlite3.connect("data/checkpoints.sqlite", check_same_thread=False)
    memory = SqliteSaver(conn)

    return workflow.compile(checkpointer=memory)
