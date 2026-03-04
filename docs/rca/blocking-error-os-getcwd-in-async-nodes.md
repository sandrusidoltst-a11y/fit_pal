# RCA: BlockingError from os.getcwd() in Async Nodes

## Problem Description

All food-logging HITL paths (confirm/reject/edit) fail with `BlockingError` when running under `langgraph dev`. The error is raised by `blockbuster`, which detects sync syscalls inside async contexts.

**Severity**: High — blocks all HITL food-logging flows (confirm, reject, edit). Non-interrupt paths (chitchat, stats) are unaffected.

## Reproduction Steps

1. Start the dev server: `langgraph dev`
2. Log a food item (e.g., "I had 200g of chicken")
3. Reach the confirmation interrupt
4. Respond with "yes" to confirm
5. `BlockingError` is raised at `confirmation_node.py:115`

## Root Cause Analysis

`os.getcwd()` is a **synchronous blocking syscall**. When called inside an async LangGraph node running on an `asyncio` event loop, it blocks the thread. The `blockbuster` library (enabled by `langgraph dev`) instruments common blocking calls and raises `BlockingError` to surface these issues early.

### Affected Files (5 nodes)

| File | Line | Call |
|---|---|---|
| `src/agents/nodes/confirmation_node.py` | 115 | `os.path.join(os.getcwd(), "prompts", "confirmation_parser.md")` |
| `src/agents/nodes/input_node.py` | 15 | `os.path.join(os.getcwd(), "prompts", "input_parser.md")` |
| `src/agents/nodes/calculate_macros_node.py` | 87 | `os.path.join(os.getcwd(), "prompts", "macro_estimation.md")` |
| `src/agents/nodes/response_node.py` | 73 | `os.path.join(os.getcwd(), "prompts", "response_generator.md")` |
| `src/agents/nodes/selection_node.py` | 37 | `os.path.join(os.getcwd(), "prompts", "agent_selection.md")` |

### Why os.getcwd() Was Used

The intent was to resolve prompt file paths relative to the project root. However, `os.getcwd()` is both:
1. **Blocking** — triggers `BlockingError` in async contexts
2. **Fragile** — depends on the working directory at runtime, which may differ from the project root

### Correct Pattern

`src/config.py` already defines `BASE_DIR` using `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`, computed once at **import time** (not inside an async function). This is deterministic and non-blocking.

## Proposed Fix

Replace all `os.getcwd()` calls with `BASE_DIR` imported from `src.config`:

```python
# Before (blocking)
prompt_path = os.path.join(os.getcwd(), "prompts", "confirmation_parser.md")

# After (non-blocking, deterministic)
from src.config import BASE_DIR
prompt_path = os.path.join(BASE_DIR, "prompts", "confirmation_parser.md")
```

Remove `import os` from files where it becomes unused after the fix.

## Validation Commands

```bash
uv run pytest tests/unit/ -v
uv run pytest tests/graph_api/ -v -s
```
