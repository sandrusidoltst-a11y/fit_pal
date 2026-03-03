"""Shared fixtures for graph-api tests. Auto-starts langgraph dev on port 2024 if not running."""
import os
import subprocess
import time
import urllib.request
import urllib.error
import atexit
import pytest
from langgraph_sdk import get_client


LANGGRAPH_DEV_URL = "http://127.0.0.1:2024"


def is_server_running(host: str = "127.0.0.1", port: int = 2024, timeout: float = 1.0) -> bool:
    """Check if the server is fully ready by hitting the /ok healthcheck endpoint."""
    try:
        req = urllib.request.Request(f"http://{host}:{port}/ok", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.getcode() == 200
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        return False


def kill_process_tree_on_port(port: int):
    """Kill the entire process tree for any process listening on the specified port."""
    try:
        if os.name == "nt":
            netstat = subprocess.check_output(
                f"netstat -ano | findstr :{port}", shell=True
            ).decode()
            pids_to_kill = set()
            for line in netstat.strip().split("\n"):
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    if len(parts) > 4:
                        pids_to_kill.add(parts[-1])

            for pid in pids_to_kill:
                print(f"[conftest] Killing process tree rooted at PID {pid} on port {port}")
                # /T kills the entire process tree, not just the parent
                subprocess.call(
                    ["taskkill", "/F", "/T", "/PID", pid],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            if pids_to_kill:
                time.sleep(1)
        else:
            subprocess.call(
                f"kill -9 $(lsof -t -i:{port})", shell=True, stderr=subprocess.DEVNULL
            )
    except subprocess.CalledProcessError:
        pass  # No process on port — nothing to kill
    except Exception as e:
        print(f"[conftest] Port cleanup warning: {e}")


def cleanup_server(process: subprocess.Popen):
    """Kill the server process and its entire child tree."""
    if process.poll() is not None:
        return

    print("\n[conftest] Tearing down auto-started langgraph dev server...")

    if os.name == "nt":
        # taskkill /T /F kills the process and all children — reliable on Windows
        subprocess.call(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        process.terminate()

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


@pytest.fixture(scope="session", autouse=True)
def auto_start_langgraph_server():
    """
    Automatically starts the langgraph dev server if it's not already running.
    Tears it down cleanly (Windows compatible) when the test session ends.
    """
    if is_server_running():
        yield
        return

    print("\n[conftest] langgraph dev server not found.")
    print("[conftest] Cleaning up any hanging processes on port 2024...")
    kill_process_tree_on_port(2024)

    print("[conftest] Starting langgraph dev server...")

    # Use DEVNULL instead of PIPE to prevent buffer deadlocks that create zombie processes
    process = subprocess.Popen(
        ["uv", "run", "langgraph", "dev"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    atexit.register(cleanup_server, process)

    # Poll until the server is ready (max 30 seconds)
    max_retries = 60
    ready = False
    for _ in range(max_retries):
        if is_server_running():
            ready = True
            print("[conftest] Server is ready!")
            break
        if process.poll() is not None:
            pytest.fail(
                f"langgraph dev server crashed on startup (exit code {process.returncode})"
            )
        time.sleep(0.5)

    if not ready:
        cleanup_server(process)
        pytest.fail("langgraph dev server failed to start within 30 seconds.")

    yield

    try:
        atexit.unregister(cleanup_server)
    except AttributeError:
        pass

    cleanup_server(process)


@pytest.fixture
def lg_client():
    """
    Returns a langgraph-sdk client connected to the local dev server.
    Fails fast if the server is inexplicably down.
    """
    if not is_server_running():
        pytest.fail("langgraph dev server went down unexpectedly.")
    return get_client(url=LANGGRAPH_DEV_URL)


@pytest.fixture
async def thread(lg_client):
    """Creates a fresh thread for each test and cleans it up after."""
    t = await lg_client.threads.create()
    yield t["thread_id"]
    await lg_client.threads.delete(t["thread_id"])
