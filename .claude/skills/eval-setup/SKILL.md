---
name: eval-setup
description: Create single-step evaluation notebooks for FitPal graph nodes. Use when the user says "create eval", "new eval", "eval setup", or wants to evaluate a specific node's quality. Guides dataset creation, example design, evaluator selection, and notebook generation.
---

# Eval Setup

Create a single-step evaluation notebook that tests a FitPal graph node in isolation using LangSmith.

## Prerequisites

Before starting, the user must create an **empty dataset in the LangSmith UI** inside their project (e.g., `fit-pal-agent`). This is required because the LangSmith SDK cannot create datasets inside a specific project — only the UI can. Ask the user for:

1. **Which node** to evaluate
2. **The dataset ID** (UUID from LangSmith UI after creating the empty dataset)
3. **The dataset name** they gave it in the UI
4. **Experiment prefix** — describes what's being tested, not which node. Examples: `gpt-4o-baseline`, `gpt-4.1-nano`, `updated-prompt-v2`

## Workflow

### Step 1 — Understand the node

Identify the node from this mapping and read its prompt file:

| Node | Prompt file | Config key |
|------|-------------|------------|
| `input_parser_node` | `prompts/input_parser.md` | `input_node` |
| `agent_selection_node` | `prompts/agent_selection.md` | `selection_node` |
| `confirmation_node` | `prompts/confirmation_parser.md` | `confirmation_node` |
| `calculate_macros_node` | `prompts/macro_estimation.md` | `estimation_node` |
| `response_node` | `prompts/response_generator.md` | `response_node` |

Also read:
- The node source file in `src/agents/nodes/` — understand what state keys it reads and returns
- `src/config.py` — check `NODE_CONFIGS` for the model and temperature
- The relevant schema in `src/schemas/` — understand the structured output format

### Step 2 — Design dataset examples

Based on the node's prompt, propose 10-20 examples that cover:
- Every action/route/outcome the node can produce
- Edge cases mentioned in the prompt
- Ambiguous inputs that could confuse the LLM
- At least 2-3 examples per action type or output category

Each example needs:
- **Input**: what the user/state provides to the node
- **Expected output**: all fields the node returns, with concrete expected values

Present the examples to the user for review. If the user suggests ideas, create similar examples in the same style. Iterate until the user is satisfied.

For date/time fields that depend on when the eval runs, use **sentinel values** instead of hardcoded dates:
- `"TODAY"` → resolves to today's date at eval time
- `"YESTERDAY_NOON"` → resolves to yesterday at 12:00
- `"RELATIVE"` → just checks the value is not None (for relative time expressions)
- `"RELATIVE_N_DAYS_AGO"` → resolves to `today - (N-1)` (inclusive of today)

### Step 3 — Choose evaluators

For each output dimension, pick the right evaluator type:

**Deterministic `==`** — for enum values, counts, or exact matches:
```python
def correct_action(outputs: dict, reference_outputs: dict) -> bool:
    return outputs["action"] == reference_outputs["action"]
```

**Tolerance-based** — for numeric values where approximate is OK (e.g., gram conversions). Return a score dict with 0.0-1.0:
```python
def amount_accuracy(outputs: dict, reference_outputs: dict) -> dict:
    # Compare within ±20% tolerance
    return {"key": "amount_accuracy", "score": fraction_within_tolerance, "comment": details}
```

**Date-aware** — for dates that depend on eval runtime. Use sentinel resolution + treat null and today as equivalent:
```python
def correct_dates(outputs: dict, reference_outputs: dict) -> bool:
    # Resolve sentinels, then compare date portions
    # Treat null and today as equivalent for start_date/end_date
```

**LLM-as-judge** — only when there's no single correct answer (e.g., food name normalization, response quality). Use `gpt-4o` with structured output:
```python
async def quality_judge(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    grade = await judge_llm.ainvoke([...])
    return {"key": "quality", "score": score, "comment": reasoning}
```

Use deterministic evaluators wherever possible — they're faster, cheaper, and more reliable. Only use LLM-as-judge for genuinely subjective dimensions.

### Step 4 — Create the notebook

Write the `.ipynb` file to `notebooks/evals/eval_<node_name>.ipynb` using the Write tool.

The notebook must have this cell structure:

1. **Markdown**: Title and overview — list which dimensions are being evaluated
2. **Code**: Environment setup — sys.path, dotenv, imports, LangSmith client
3. **Markdown**: Dataset section header
4. **Code**: Examples list + upload to dataset (using `dataset_id` from user, skip upload if examples exist)
5. **Markdown**: Target function header
6. **Code**: Target function — calls the node directly with minimal state, returns structured dict
7. **Code**: Smoke test — run target function on one example, print result
8. **Markdown**: Evaluators header
9. **Code cells**: One cell per evaluator
10. **Markdown**: Run evaluation header
11. **Code**: `client.aevaluate()` with all evaluators + `experiment_results.to_pandas()`
12. **Markdown**: Notes

#### Target function pattern

The target function calls the node directly as a Python function — no server, no HTTP. It wraps the node in an async function (required by `aevaluate`):

```python
async def run_<node_name>(inputs: dict) -> dict:
    state = {<minimal state for the node>}
    result = <node_function>(state)
    return {<structured outputs for evaluators>}
```

#### Evaluation cell pattern

```python
experiment_results = await client.aevaluate(
    run_<node_name>,
    data=dataset_id,
    evaluators=[evaluator1, evaluator2, ...],
    experiment_prefix="<user-provided-prefix>",
    max_concurrency=4,
)
experiment_results.to_pandas()
```

### Step 5 — Verify

After creating the notebook, tell the user to:
1. Open the notebook in VS Code
2. Select the FitPal kernel (`FitPal (uv)`)
3. Run cells top to bottom
4. Check LangSmith for the experiment results

## Reference

- Existing eval notebook: `notebooks/evals/eval_input_parser.ipynb` — read this for the full pattern if needed
- Eval debugger skill: use `/eval-debugger <experiment-name>` after running to analyze failures
- Reports are saved to `notebooks/evals/reports/` (gitignored)

## Important Rules

- The notebook calls nodes **directly as Python functions** — no LangGraph server needed
- Datasets must be created in the **LangSmith UI** inside the project — the SDK cannot do this
- The `experiment_prefix` describes **what's being tested** (model, prompt change), not which node — the dataset name already identifies the node
- Always include a **smoke test cell** before the full eval run
- Sentinel values for dates resolve at eval time — never hardcode dates in examples
