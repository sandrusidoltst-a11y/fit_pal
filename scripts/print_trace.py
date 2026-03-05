"""Fetch and print the full conversation flow for a LangSmith thread.

Usage:
    uv run scripts/print_trace.py <thread-id>                # Full conversation flow
    uv run scripts/print_trace.py <thread-id> --compact      # Compact (no node detail)
    uv run scripts/print_trace.py <thread-id> --raw          # Raw JSON dump

Save to file:
    uv run scripts/print_trace.py <thread-id> > traces/my_thread.txt
    uv run scripts/print_trace.py <thread-id> --raw > traces/my_thread.json
"""

import json
import os
import sys
import textwrap
from datetime import datetime

from dotenv import load_dotenv


# ── Helpers ──────────────────────────────────────────────────────────────────

def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def _wrap(text: str, indent: int = 4, width: int = 100) -> str:
    """Wrap text with hanging indent."""
    prefix = " " * indent
    return textwrap.fill(str(text), width=width, initial_indent=prefix,
                         subsequent_indent=prefix)


def _extract_messages(data: dict | None) -> list[dict]:
    """Pull message list from run inputs/outputs (handles LangGraph shapes)."""
    if not data:
        return []
    # LangGraph stores messages under "messages" or sometimes "input"/"output"
    if "messages" in data:
        msgs = data["messages"]
        if isinstance(msgs, list):
            return msgs
    return []


def _format_message(msg) -> str:
    """Format a single LangChain-style message dict for display."""
    if isinstance(msg, str):
        return msg

    # Handle (role, content) tuples from some serializations
    if isinstance(msg, (list, tuple)) and len(msg) == 2:
        return f"[{msg[0]}] {msg[1]}"

    if not isinstance(msg, dict):
        return str(msg)

    role = msg.get("type", msg.get("role", "unknown"))
    content = msg.get("content", "")
    name = msg.get("name", "")

    # Tool calls embedded in AI messages
    tool_calls = msg.get("tool_calls") or msg.get("additional_kwargs", {}).get("tool_calls", [])

    parts = []
    if content:
        label = role.upper()
        if name:
            label += f" ({name})"
        parts.append(f"  [{label}] {content}")

    for tc in tool_calls:
        if isinstance(tc, dict):
            tc_name = tc.get("name", tc.get("function", {}).get("name", "?"))
            tc_args = tc.get("args", tc.get("function", {}).get("arguments", ""))
            if isinstance(tc_args, dict):
                tc_args = json.dumps(tc_args, default=_json_default)
            parts.append(f"  [TOOL_CALL] {tc_name}({tc_args})")

    return "\n".join(parts) if parts else f"  [{role.upper()}] {json.dumps(msg, default=_json_default)[:300]}"


# ── Core ─────────────────────────────────────────────────────────────────────

def print_thread_flow(client, thread_id: str, *, compact: bool = False, raw: bool = False):
    """Fetch all runs for a thread and print the full conversation flow."""
    project = os.environ.get("LANGCHAIN_PROJECT", os.environ.get("LANGSMITH_PROJECT", "default"))

    # Fetch top-level (root) runs for this thread
    # LangSmith stores thread IDs under session_id, conversation_id, or thread_id
    filter_str = (
        f'and(in(metadata_key, ["session_id","conversation_id","thread_id"]), '
        f'eq(metadata_value, "{thread_id}"))'
    )
    runs = list(client.list_runs(
        project_name=project,
        filter=filter_str,
        is_root=True,
        limit=100,
    ))

    if not runs:
        # Fallback: drop is_root filter
        runs = list(client.list_runs(
            project_name=project,
            filter=filter_str,
            limit=100,
        ))

    if not runs:
        print(f"No runs found for thread_id='{thread_id}' in project='{project}'")
        sys.exit(1)

    # Sort by start time (chronological conversation order)
    runs.sort(key=lambda r: r.start_time or datetime.min)

    total_tokens = sum((r.total_tokens or 0) for r in runs)
    total_duration = sum(
        ((r.end_time - r.start_time).total_seconds() if r.start_time and r.end_time else 0)
        for r in runs
    )

    print("=" * 80)
    print(f"  THREAD: {thread_id}")
    print(f"  Project: {project}")
    print(f"  Turns: {len(runs)}  |  Total tokens: {total_tokens}  |  Duration: {total_duration:.1f}s")
    print("=" * 80)

    for turn_idx, run in enumerate(runs, 1):
        status = "OK" if run.status == "success" else (run.status or "?").upper()
        duration = ""
        if run.start_time and run.end_time:
            dt = (run.end_time - run.start_time).total_seconds()
            duration = f"{dt:.1f}s"

        print(f"\n{'-' * 80}")
        print(f"  TURN {turn_idx}  |  {run.name}  |  {status}  |  {duration}")
        print(f"  Run ID: {run.id}")
        if run.start_time:
            print(f"  Time:   {run.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'-' * 80}")

        if raw:
            print("\n  INPUTS:")
            print(json.dumps(run.inputs, indent=2, default=_json_default))
            print("\n  OUTPUTS:")
            print(json.dumps(run.outputs, indent=2, default=_json_default))
            continue

        # ── Show input messages (what the user sent this turn) ───────────
        in_msgs = _extract_messages(run.inputs)
        if in_msgs:
            print("\n  INPUT MESSAGES:")
            for m in in_msgs:
                print(_format_message(m))
        elif run.inputs:
            # Non-message input (e.g., resume command for HITL)
            inp_str = json.dumps(run.inputs, default=_json_default)
            if len(inp_str) > 500:
                inp_str = inp_str[:500] + "..."
            print(f"\n  INPUT: {inp_str}")

        # ── Show output messages (what the agent responded) ──────────────
        out_msgs = _extract_messages(run.outputs)
        if out_msgs:
            print("\n  OUTPUT MESSAGES:")
            for m in out_msgs:
                print(_format_message(m))
        elif run.outputs:
            out_str = json.dumps(run.outputs, default=_json_default)
            if len(out_str) > 1000:
                out_str = out_str[:1000] + "..."
            print(f"\n  OUTPUT: {out_str}")

        # ── Show error if any ────────────────────────────────────────────
        if run.error:
            print(f"\n  ERROR: {run.error}")

        # ── Show node-level execution (child runs) ───────────────────────
        if not compact:
            children = list(client.list_runs(
                project_name=project,
                parent_run_id=run.id,
                limit=100,
            ))
            children.sort(key=lambda r: r.start_time or datetime.min)

            if children:
                print(f"\n  NODE EXECUTION ({len(children)} steps):")
                for child in children:
                    c_status = "OK" if child.status == "success" else (child.status or "?")
                    c_dur = ""
                    if child.start_time and child.end_time:
                        c_dt = (child.end_time - child.start_time).total_seconds()
                        c_dur = f" ({c_dt:.1f}s)"
                    c_tokens = f" [{child.total_tokens}tok]" if child.total_tokens else ""

                    icon = "+" if c_status == "OK" else "x"
                    print(f"    {icon} {child.name} [{child.run_type}]{c_dur}{c_tokens}")

                    if child.error:
                        print(f"      ERROR: {child.error[:200]}")

                    # Show tool inputs/outputs for tool runs
                    if child.run_type == "tool" and child.inputs:
                        tool_inp = json.dumps(child.inputs, default=_json_default)
                        if len(tool_inp) > 300:
                            tool_inp = tool_inp[:300] + "..."
                        print(f"      input:  {tool_inp}")
                    if child.run_type == "tool" and child.outputs:
                        tool_out = json.dumps(child.outputs, default=_json_default)
                        if len(tool_out) > 300:
                            tool_out = tool_out[:300] + "..."
                        print(f"      output: {tool_out}")

    print(f"\n{'=' * 80}")
    print(f"  END OF THREAD ({len(runs)} turns)")
    print(f"{'=' * 80}\n")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    load_dotenv()

    # Map LANGCHAIN_API_KEY -> LANGSMITH_API_KEY if needed
    if not os.environ.get("LANGSMITH_API_KEY"):
        langchain_key = os.environ.get("LANGCHAIN_API_KEY")
        if langchain_key:
            os.environ["LANGSMITH_API_KEY"] = langchain_key

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        sys.exit(0)

    thread_id = sys.argv[1]
    compact = "--compact" in sys.argv
    raw = "--raw" in sys.argv

    from langsmith import Client
    client = Client()

    print_thread_flow(client, thread_id, compact=compact, raw=raw)


if __name__ == "__main__":
    main()
