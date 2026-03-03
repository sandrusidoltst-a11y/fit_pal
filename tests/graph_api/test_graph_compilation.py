"""
Graph compilation tests for the FitPal nutritionist graph (`nutritionist.py`).

Scope:
    Verifies that the full graph compiles without errors and all expected
    nodes are registered. Does NOT require the langgraph dev server.

LLM Usage:
    NONE — no LLM calls. Pure graph structure validation.
"""
import pytest
from langgraph.checkpoint.memory import MemorySaver
from src.agents.nutritionist import define_graph


@pytest.mark.asyncio
async def test_graph_compiles_with_checkpointer():
    """
    arrange: A real MemorySaver checkpointer.
    act:     Compile the graph with the checkpointer.
    assert:  Graph object is returned without errors.
    """
    memory = MemorySaver()
    graph = await define_graph(checkpointer=memory)
    assert graph is not None


@pytest.mark.asyncio
async def test_graph_has_all_expected_nodes():
    """
    arrange: A compiled graph with MemorySaver.
    act:     Inspect the registered node names.
    assert:  All six expected nodes are present.
    """
    memory = MemorySaver()
    graph = await define_graph(checkpointer=memory)

    node_names = set(graph.nodes.keys())
    expected = {"input_parser", "food_search", "agent_selection", "calculate_log", "stats_lookup", "response"}
    assert expected.issubset(node_names), f"Missing nodes: {expected - node_names}"
