"""Shared fixtures for graph-api tests. Requires langgraph dev running on port 2024."""
import os
import subprocess
import time
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


def kill_processes_on_port(port: int):
    """Attempt to kill any process listening on the specified port. Windows-focused."""
    try:
        if os.name == 'nt':
            # Run netstat to find PID
            netstat = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True).decode()
            pids_to_kill = set()
            for line in netstat.strip().split('\n'):
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    if len(parts) > 4:
                        pids_to_kill.add(parts[-1])
            
            for pid in pids_to_kill:
                print(f"[conftest] Killing zombie process {pid} on port {port}")
                subprocess.call(["taskkill", "/F", "/PID", pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(0.5) 
        else:
            # Linux/Mac fallback
            subprocess.call(f"kill -9 $(lsof -t -i:{port})", shell=True, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[conftest] Port cleanup warning (can usually be ignored): {e}")


def cleanup_server(process: subprocess.Popen):
    """Safely terminate the server process."""
    if process.poll() is not None:
        return  # Process is already dead

    print("\n[conftest] Tearing down auto-started langgraph dev server...")
    if os.name == "nt":
        # Send CTRL_BREAK_EVENT to the process group on Windows
        import signal
        try:
            os.kill(process.pid, signal.CTRL_BREAK_EVENT)
        except ProcessLookupError:
            pass
    else:
        process.terminate()

    # Wait gracefully
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture(scope="session", autouse=True)
def auto_start_langgraph_server():
    """
    Automatically starts the langgraph dev server if it's not already running.
    Tears it down cleanly (Windows compatible) when the test session ends.
    """
    if is_server_running():
        # Server is already running (likely launched manually in another terminal)
        yield
        return

    print("\n[conftest] langgraph dev server not found.")
    print(f"[conftest] Cleaning up any hanging processes on port 2024...")
    kill_processes_on_port(2024)
    time.sleep(1) # Give OS brief moment to free port
    
    print("[conftest] Starting langgraph dev server...")

    # Start the server as a subprocess
    # Note: On Windows, use creationflags to create a new process group for clean termination
    process_kwargs = {}
    if os.name == "nt":
        # CREATE_NEW_PROCESS_GROUP is necessary on Windows to send CTRL_BREAK_EVENT
        process_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    # Use uv run to ensure the right environment is used
    process = subprocess.Popen(
        ["uv", "run", "langgraph", "dev"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **process_kwargs
    )

    # Register the cleanup handler to ensure it runs even if pytest crashes or is interrupted
    atexit.register(cleanup_server, process)

    # Poll until the server is ready (max 15 seconds)
    max_retries = 30
    ready = False
    for _ in range(max_retries):
        if is_server_running():
            ready = True
            print("[conftest] Server is ready!")
            break
        # Check if process crashed immediately
        if process.poll() is not None:
            _, err = process.communicate()
            pytest.fail(f"langgraph dev server crashed on startup: {err.decode()}")
        time.sleep(0.5)

    if not ready:
        cleanup_server(process)
        pytest.fail("langgraph dev server failed to start within 15 seconds.")

    # Yield control to the tests
    yield

    # Normal Teardown: terminate the server
    # We call atexit.unregister to prevent double-execution, although the poll() check in 
    # cleanup_server makes double-execution safe anyway.
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
