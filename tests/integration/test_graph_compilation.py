"""Integration test for graph compilation."""
import pytest
from langgraph.checkpoint.memory import MemorySaver
from src.agents.nutritionist import define_graph

@pytest.mark.asyncio
async def test_graph_compiles_with_checkpointer():
    """Integration test: graph compiles with a real checkpointer."""
    memory = MemorySaver()
    graph = await define_graph(checkpointer=memory)
    assert graph is not None

@pytest.mark.asyncio
async def test_graph_has_all_expected_nodes():
    """Verify all nodes are registered in the compiled graph."""
    memory = MemorySaver()
    graph = await define_graph(checkpointer=memory)
    
    node_names = set(graph.nodes.keys())
    expected = {"input_parser", "food_search", "agent_selection", "calculate_log", "stats_lookup", "response"}
    assert expected.issubset(node_names), f"Missing nodes: {expected - node_names}"
