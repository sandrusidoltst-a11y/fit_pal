import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from src.agents.nodes.food_search_node import food_search_node
from src.agents.nodes.input_node import input_parser_node
from src.agents.nodes.selection_node import agent_selection_node
from src.agents.state import AgentState


def define_graph():
    # Initialize the graph with the AgentState
    workflow = StateGraph(AgentState)

    # Placeholder nodes (to be replaced in future phases)
    def stats_lookup_node(state: AgentState):
        return {"messages": ["Calculating daily statistics..."]}

    def response_node(state: AgentState):
        return {"messages": ["Response placeholder"]}

    def route_parser(state: AgentState):
        action = state.get("last_action")
        if action in ["LOG_FOOD", "QUERY_FOOD_INFO"]:
            return "food_search"
        elif action == "QUERY_DAILY_STATS":
            return "stats_lookup"
        return "response"

    workflow.add_node("input_parser", input_parser_node)
    workflow.add_node("food_search", food_search_node)
    workflow.add_node("agent_selection", agent_selection_node)
    workflow.add_node("stats_lookup", stats_lookup_node)
    workflow.add_node("response", response_node)

    workflow.set_entry_point("input_parser")

    workflow.add_conditional_edges(
        "input_parser",
        route_parser,
        {
            "food_search": "food_search",
            "stats_lookup": "stats_lookup",
            "response": "response",
        },
    )

    workflow.add_edge("food_search", "agent_selection")
    workflow.add_edge("agent_selection", "response")
    workflow.add_edge("stats_lookup", "response")
    workflow.add_edge("response", END)

    conn = sqlite3.connect("data/checkpoints.sqlite", check_same_thread=False)
    memory = SqliteSaver(conn)

    return workflow.compile(checkpointer=memory)
