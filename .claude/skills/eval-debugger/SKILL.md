---
name: eval-debugger
description: Debug and report on eval failures from LangSmith experiments. Use when the user says "debug eval", "eval report", "eval failures", or "clean eval reports".
argument-hint: <experiment-name> | clean
---

# Eval Debugger

Debug failing eval runs from LangSmith experiments, generate diagnostic reports, and analyze root causes.

## Modes

### Debug Mode

**Trigger**: User provides an experiment name (e.g., "debug eval input-parser-eval-abc123")

**If user doesn't provide an experiment name, ASK for it. Do not guess.**

**Step 1 — Fetch failures**:
```bash
uv run .claude/skills/eval-debugger/scripts/fetch_eval_failures.py <experiment-name>
```
This outputs a markdown report to stdout and saves it to `notebooks/evals/reports/YYYY-MM-DD_<experiment-name>.md`.

**Step 2 — Read the saved report file** from `notebooks/evals/reports/`.

**Step 3 — Identify the node** being evaluated by matching the experiment name to this mapping:

| Experiment contains | Prompt file | Node config key |
|---------------------|-------------|-----------------|
| `input-parser` | `prompts/input_parser.md` | `input_node` |
| `agent-selection` | `prompts/agent_selection.md` | `selection_node` |
| `confirmation` | `prompts/confirmation_parser.md` | `confirmation_node` |
| `macro-estimation` | `prompts/macro_estimation.md` | `estimation_node` |
| `response` | `prompts/response_generator.md` | `response_node` |

If the experiment name doesn't match any pattern, ask the user which node/prompt it tests.

**Step 4 — Read context files**:
- Read the relevant prompt file identified in Step 3
- Read `src/config.py` and find the `NODE_CONFIGS` entry for the node to get model and temperature

**Step 5 — Diagnose each failure**. Classify into one of:

- **PROMPT_GAP**: The prompt doesn't cover this case or is ambiguous. The model behaved reasonably given the instructions, but the instructions are incomplete.
- **MODEL_ISSUE**: The prompt is clear but the model failed to follow it. Suggests a capability limitation or need for a stronger model.
- **JUDGE_TOO_STRICT**: The evaluator or LLM-as-judge rejected a valid output. The node output was reasonable but the evaluator criteria are too narrow.
- **DATASET_EXPECTATION**: The expected output in the dataset is wrong or unreasonable. The node actually produced the correct result.

**Step 6 — Summarize in chat** with:
- Overall pass/fail stats
- Each failure with diagnosis and actionable suggestion
- If multiple failures share a root cause, group them

### Clean Mode

**Trigger**: User says "clean eval reports" or "clear eval reports"

```bash
uv run .claude/skills/eval-debugger/scripts/clean_reports.py
```

## Report Location

Reports are saved to `notebooks/evals/reports/` (gitignored). The user can inspect them directly.
