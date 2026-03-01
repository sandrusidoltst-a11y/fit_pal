"""Shared fixtures for graph-api tests. Requires langgraph dev running on port 2024."""
import pytest
from langgraph_sdk import get_client


LANGGRAPH_DEV_URL = "http://127.0.0.1:2024"


@pytest.fixture
def lg_client():
    """
    Returns a langgraph-sdk client connected to the local dev server.
    Skips the test with a clear message if the server is not running.
    """
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(2)
        sock.connect(("127.0.0.1", 2024))
    except (ConnectionRefusedError, OSError):
        pytest.skip(
            "langgraph dev server not running. "
            "Start it with: uv run langgraph dev"
        )
    finally:
        sock.close()
    return get_client(url=LANGGRAPH_DEV_URL)


@pytest.fixture
async def thread(lg_client):
    """Creates a fresh thread for each test and cleans it up after."""
    t = await lg_client.threads.create()
    yield t["thread_id"]
    await lg_client.threads.delete(t["thread_id"])
