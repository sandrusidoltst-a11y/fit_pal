# Orphaned LangGraph Dev Server

## What is the problem?

When you run `langgraph dev` (manually or via test conftest), it spawns a process tree listening on port 2024. If the terminal is closed, the session crashes, or Ctrl+C doesn't propagate cleanly, these processes can survive as "orphans" — still holding the port but no longer attached to any terminal.

**Symptoms:**
- `langgraph dev` fails to start with "port 2024 already in use"
- Graph-api tests hang or fail on startup
- You don't have any visible terminal running the server

## When does this happen?

| Scenario | Why it orphans |
|---|---|
| Manual `langgraph dev` in a terminal that gets closed | Process isn't killed when terminal disappears |
| Test run interrupted (Ctrl+C, crash, forced kill) | conftest `cleanup_server` teardown never fires |
| Claude Code or IDE spawns `langgraph dev` during a session | Session ends without cleanup |

This is a Windows-specific issue — `taskkill /F` on a parent doesn't always cascade to child processes unless `/T` is used.

## How to find the orphan

### 1. Check if anything is listening on port 2024

```bash
netstat -ano | grep 2024
```

Look for a line with `LISTENING` — the last column is the **PID** (process ID).

Example output:
```
TCP    127.0.0.1:2024    0.0.0.0:0    LISTENING    23652
```

### 2. Identify the process

```bash
tasklist //FI "PID eq <pid>"
```

Confirms the process name (usually `python.exe` for langgraph dev).

### 3. See the full command line (optional)

```bash
wmic process where "ProcessId=<pid>" get CommandLine /format:list
```

Shows exactly what command started the process (e.g., `langgraph dev --no-browser`).

## How to kill it

```bash
taskkill //F //T //PID <pid>
```

| Flag | Meaning |
|---|---|
| `//F` | Force kill (don't ask the process to exit gracefully) |
| `//T` | Kill the entire process **tree** (parent + all children) |
| `//PID` | Target a specific process by its ID |

You only need to kill the **topmost parent** — `/T` will cascade to all children.

### Verify it's gone

```bash
netstat -ano | grep 2024
```

No output = port is free.