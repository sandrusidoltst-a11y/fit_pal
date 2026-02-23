from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, StateGraph

from src.agents.nodes.calculate_log_node import calculate_log_node
from src.agents.nodes.food_search_node import food_search_node
from src.agents.nodes.input_node import input_parser_node
from src.agents.nodes.response_node import response_node
from src.agents.nodes.selection_node import agent_selection_node
from src.agents.nodes.stats_node import stats_lookup_node
from src.agents.state import AgentState, InputState, OutputState


async def define_graph():
    # Initialize the graph with the AgentState
    workflow = StateGraph(state_schema=AgentState, input_schema=InputState, output_schema=OutputState)

    def route_parser(state: AgentState):
        action = state.get("last_action")
        if action in ["LOG_FOOD", "QUERY_FOOD_INFO"]:
            return "food_search"
        elif action == "QUERY_DAILY_STATS":
            return "stats_lookup"
        return "response"

    def route_after_selection(state: AgentState):
        """Route based on selection result."""
        action = state.get("last_action")
        if action == "SELECTED":
            return "calculate_log"
        else:  # NO_MATCH
            return "response"

    def route_after_calculate(state: AgentState):
        """Route back to food_search if more items pending, else to response."""
        if state.get("pending_food_items", []):
            return "food_search"  # Process next item
        else:
            return "response"  # All items processed

    workflow.add_node("input_parser", input_parser_node)
    workflow.add_node("food_search", food_search_node)
    workflow.add_node("agent_selection", agent_selection_node)
    workflow.add_node("calculate_log", calculate_log_node)
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

    workflow.add_conditional_edges(
        "agent_selection",
        route_after_selection,
        {
            "calculate_log": "calculate_log",
            "response": "response",
        },
    )

    workflow.add_conditional_edges(
        "calculate_log",
        route_after_calculate,
        {
            "food_search": "food_search",
            "response": "response",
        },
    )

    workflow.add_edge("stats_lookup", "response")
    workflow.add_edge("response", END)

    memory = AsyncSqliteSaver.from_conn_string("data/checkpoints.sqlite")

    return workflow.compile(checkpointer=memory)
