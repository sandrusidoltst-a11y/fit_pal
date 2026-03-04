"""
E2E flow tests for the FitPal graph via HTTP API.

Scope:
    Every test goes through the real langgraph dev server (auto-started by conftest).
    This matches the LangSmith Studio execution path, so BlockingErrors that appear
    in Studio will also appear here.

LLM Usage:
    LIVE — all LLM calls are real. Run deliberately, not in pre-commit gate.

HITL Pattern:
    Food-logging paths hit interrupt() at confirmation_node. Tests use a two-turn
    pattern: Turn 1 sends food input (pauses at interrupt), Turn 2 resumes with
    confirm/reject/edit via command={"resume": "<text>"}.
"""

from pathlib import Path

import pytest

from graph_api import conftest as _conftest


ASSISTANT_ID = "fitpal"  # Must match the graph name in langgraph.json
LOGS_DIR = Path(__file__).parent / "logs"


def _extract_server_traceback(error_type="BlockingError"):
    """Read the server log file and extract the most recent traceback for error_type.

    Strategy: find the last line containing the error_type, then walk backwards
    to find the "Traceback (most recent call last):" header.
    """
    log_path = _conftest._server_log_path
    if log_path is None or not log_path.exists():
        return None

    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None

    error_indices = [i for i, line in enumerate(lines) if error_type in line]
    if not error_indices:
        return None

    last_error_idx = error_indices[-1]
    traceback_start = None
    for i in range(last_error_idx, -1, -1):
        if "Traceback (most recent call last):" in lines[i]:
            traceback_start = i
            break

    if traceback_start is None:
        return None

    return "\n".join(lines[traceback_start : last_error_idx + 1])


def _dump_error_log(thread, error_type, test_name="unknown"):
    """Extract the server traceback and save as a plain .txt file."""
    LOGS_DIR.mkdir(exist_ok=True)
    filepath = LOGS_DIR / f"{test_name}_{thread[:8]}.txt"

    header = f"Test: {test_name}\nThread: {thread}\nError: {error_type}\n"
    traceback_text = _extract_server_traceback(error_type)

    content = header + "\n" + (traceback_text or "(no server traceback captured)")
    filepath.write_text(content, encoding="utf-8")
    return filepath


async def _run(lg_client, thread, *, input=None, command=None, test_name="unknown"):
    """Execute a graph run via HTTP and fail clearly on BlockingError.

    Uses raise_error=False so we get the raw error dict instead of an opaque
    Exception. On any error, saves the server traceback to a .txt file,
    then calls pytest.fail() with the log path.
    """
    kwargs = {"raise_error": False}
    if input is not None:
        kwargs["input"] = input
    if command is not None:
        kwargs["command"] = command

    result = await lg_client.runs.wait(thread, ASSISTANT_ID, **kwargs)

    if isinstance(result, dict) and "__error__" in result:
        err = result["__error__"]
        error_type = err.get("error", "Unknown")
        error_msg = err.get("message", "")

        logfile = _dump_error_log(thread, error_type, test_name)

        if error_type == "BlockingError":
            pytest.fail(
                f"BlockingError detected (sync call inside async context).\n"
                f"Thread: {thread}\n"
                f"Traceback: {logfile}"
            )
        else:
            pytest.fail(
                f"Graph error: {error_type}: {error_msg}\n"
                f"Thread: {thread}\n"
                f"Traceback: {logfile}"
            )

    return result


async def _assert_interrupted(lg_client, thread):
    """Verify the graph is paused at an interrupt (confirmation_node)."""
    state = await lg_client.threads.get_state(thread)
    tasks = state.get("tasks", [])
    assert tasks, (
        f"Expected graph to pause at interrupt but it didn't.\n"
        f"Thread: {thread}\n"
        f"Next: {state.get('next', [])}"
    )
    return state


# ---------------------------------------------------------------------------
# Non-interrupt paths (single turn, complete without HITL)
# ---------------------------------------------------------------------------


class TestNonInterruptPaths:
    """Paths that complete in a single turn without hitting interrupt()."""

    async def test_chitchat(self, lg_client, thread):
        """
        arrange: A plain greeting with no food or stats intent.
        act:     Graph routes directly to response node.
        assert:  No error, at least 2 messages, non-empty last message.
        """
        result = await _run(
            lg_client, thread,
            input={"messages": [{"role": "human", "content": "Hello, how are you?"}]},
        )

        messages = result.get("messages", [])
        assert len(messages) >= 2
        assert messages[-1]["content"].strip() != ""

    async def test_stats_query(self, lg_client, thread):
        """
        arrange: User asks for today's nutritional stats.
        act:     Graph routes through stats_lookup to response.
        assert:  No error, at least 2 messages, non-empty last message.
        """
        result = await _run(
            lg_client, thread,
            input={"messages": [{"role": "human", "content": "What did I eat today?"}]},
        )

        messages = result.get("messages", [])
        assert len(messages) >= 2
        assert messages[-1]["content"].strip() != ""


# ---------------------------------------------------------------------------
# Food logging — confirm flow (2 turns: log → confirm)
# ---------------------------------------------------------------------------


class TestFoodLoggingConfirm:
    """Food logging paths: Turn 1 hits HITL interrupt, Turn 2 confirms."""

    async def test_single_db_item_confirm(self, lg_client, thread):
        """
        arrange: User logs a common food item found in the DB.
        act:     Turn 1 hits interrupt at confirmation_node.
                 Turn 2 confirms → commit → response.
        assert:  Turn 1 interrupted, Turn 2 completes with non-empty response.
        """
        tn = "test_single_db_item_confirm"
        await _run(
            lg_client, thread,
            input={"messages": [{"role": "human", "content": "I ate 200g of chicken"}]},
            test_name=tn,
        )
        await _assert_interrupted(lg_client, thread)

        result = await _run(lg_client, thread, command={"resume": "yes"}, test_name=tn)

        messages = result.get("messages", [])
        assert len(messages) >= 2
        assert messages[-1]["content"].strip() != ""

    async def test_off_menu_item_confirm(self, lg_client, thread):
        """
        arrange: User logs a food not in the DB (triggers LLM estimation).
        act:     Turn 1 hits interrupt with estimated macros.
                 Turn 2 confirms → commit → response.
        assert:  Turn 1 interrupted, Turn 2 completes with non-empty response.
        """
        tn = "test_off_menu_item_confirm"
        await _run(
            lg_client, thread,
            input={"messages": [{"role": "human", "content": "I ate 200g of dragon fruit açaí bowl"}]},
            test_name=tn,
        )
        await _assert_interrupted(lg_client, thread)

        result = await _run(lg_client, thread, command={"resume": "yes"}, test_name=tn)

        messages = result.get("messages", [])
        assert len(messages) >= 2
        assert messages[-1]["content"].strip() != ""

    async def test_multi_item_confirm(self, lg_client, thread):
        """
        arrange: User logs two food items in a single message.
        act:     Turn 1 processes items via multi-item loop, hits interrupt.
                 Turn 2 confirms batch → commit → response.
        assert:  Turn 1 interrupted, Turn 2 completes with non-empty response.
        """
        tn = "test_multi_item_confirm"
        await _run(
            lg_client, thread,
            input={"messages": [{"role": "human", "content": "I had 150g of chicken and 100g of rice"}]},
            test_name=tn,
        )
        await _assert_interrupted(lg_client, thread)

        result = await _run(lg_client, thread, command={"resume": "yes"}, test_name=tn)

        messages = result.get("messages", [])
        assert len(messages) >= 2
        assert messages[-1]["content"].strip() != ""


# ---------------------------------------------------------------------------
# Food logging — reject flow (2 turns: log → reject)
# ---------------------------------------------------------------------------


class TestFoodLoggingReject:
    """Food logging paths: Turn 1 hits HITL interrupt, Turn 2 rejects."""

    async def test_single_item_reject(self, lg_client, thread):
        """
        arrange: User logs a common food item.
        act:     Turn 1 hits interrupt at confirmation_node.
                 Turn 2 rejects → routes to response (no commit).
        assert:  Turn 1 interrupted, Turn 2 completes with non-empty response.
        """
        tn = "test_single_item_reject"
        await _run(
            lg_client, thread,
            input={"messages": [{"role": "human", "content": "I ate 200g of chicken"}]},
            test_name=tn,
        )
        await _assert_interrupted(lg_client, thread)

        result = await _run(lg_client, thread, command={"resume": "no cancel it"}, test_name=tn)

        messages = result.get("messages", [])
        assert len(messages) >= 2
        assert messages[-1]["content"].strip() != ""


# ---------------------------------------------------------------------------
# Food logging — edit flow (3 turns: log → edit → confirm)
# ---------------------------------------------------------------------------


class TestFoodLoggingEdit:
    """Food logging paths: Turn 1 hits interrupt, Turn 2 edits, Turn 3 confirms."""

    async def test_edit_then_confirm(self, lg_client, thread):
        """
        arrange: User logs a common food item.
        act:     Turn 1 hits interrupt at confirmation_node.
                 Turn 2 edits amount → re-interrupts with updated batch.
                 Turn 3 confirms → commit → response.
        assert:  Turn 2 re-interrupts, Turn 3 completes with non-empty response.
        """
        tn = "test_edit_then_confirm"
        # Turn 1 — log food, hits interrupt
        await _run(
            lg_client, thread,
            input={"messages": [{"role": "human", "content": "I ate 200g of chicken"}]},
            test_name=tn,
        )
        await _assert_interrupted(lg_client, thread)

        # Turn 2 — edit, should re-interrupt
        await _run(lg_client, thread, command={"resume": "change chicken to 300g"}, test_name=tn)
        await _assert_interrupted(lg_client, thread)

        # Turn 3 — confirm edited batch
        result = await _run(lg_client, thread, command={"resume": "yes confirm"}, test_name=tn)

        messages = result.get("messages", [])
        assert len(messages) >= 2
        assert messages[-1]["content"].strip() != ""


# ---------------------------------------------------------------------------
# Conversation memory
# ---------------------------------------------------------------------------


class TestConversationMemory:
    """Verifies thread-bound state persistence across multiple runs."""

    async def test_memory_persists_across_turns(self, lg_client, thread):
        """
        arrange: First run introduces a name on the thread.
        act:     Second run asks for the name on the same thread.
        assert:  Full thread state shows both turns and agent recalls the name.
        """
        # Turn 1 — introduce a name
        result1 = await _run(
            lg_client, thread,
            input={"messages": [{"role": "human", "content": "Hi, my name is Bob"}]},
        )
        messages1 = result1.get("messages", [])
        assert len(messages1) >= 2

        # Wait for thread to be idle before starting the second run
        thread_info = await lg_client.threads.get(thread)
        assert thread_info["status"] == "idle"

        # Turn 2 — ask for the name
        result2 = await _run(
            lg_client, thread,
            input={"messages": [{"role": "human", "content": "What's my name?"}]},
        )
        messages2 = result2.get("messages", [])
        assert len(messages2) >= 2

        # Verify full accumulated thread state
        state = await lg_client.threads.get_state(thread)
        messages = state["values"]["messages"]
        assert len(messages) >= 4
        assert "Bob" in messages[-1]["content"]
