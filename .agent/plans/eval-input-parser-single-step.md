
# Feature: Single-Step Evaluation — Input Parser Node

The following plan should be complete, but validate documentation and codebase patterns before implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files.

## Feature Description

Create an interactive Jupyter notebook that evaluates the `input_parser_node` in isolation using LangSmith's evaluation framework. One dataset ("FitPal: Input Parser") with ~15 examples covering all 4 action types. Five evaluators run on every example: action classification (==), item count (==), amount accuracy (±20%), date parsing (==), and food name quality (LLM-as-judge). Results are tracked in LangSmith via `client.aevaluate()`.

## User Story

As a developer maintaining FitPal
I want to systematically evaluate the input parser's quality across many inputs
So that I can catch prompt regressions, model changes, and edge case failures before they reach users

## Problem Statement

The input parser is the most critical node — if it misclassifies intent or extracts wrong data, the entire graph fails. Currently there's no systematic way to measure its quality across a diverse set of inputs, track regressions over time, or compare performance across model/prompt changes.

## Solution Statement

A Jupyter notebook that creates a LangSmith dataset, defines a target function calling `input_parser_node` directly, runs 5 evaluators per example, and displays results as a pandas DataFrame. Each run creates a LangSmith experiment for historical comparison.

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: Medium
**Primary Systems Affected**: `notebooks/evals/`, LangSmith
**Dependencies**: `langsmith` (already installed), `langchain` (already installed)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

- `src/agents/nodes/input_node.py` — The node under test. Note: it's a sync function (not async), reads `state["messages"][-1]`, returns dict with keys: `pending_food_items`, `last_action`, `processing_results`, `consumed_at`, `start_date`, `end_date`
- `src/schemas/input_schema.py` — `FoodIntakeEvent`, `SingleFoodItem`, `ActionType` enum. These define the structured output schema.
- `prompts/input_parser.md` — System prompt. Defines all parsing rules: meal decomposition, gram conversion, search-friendly naming, date extraction hierarchy.
- `src/config.py` — `get_llm_for_node("input_node")` returns GPT-4o at temperature 0.0. Also has `BASE_DIR` used by the node for prompt loading.
- `notebooks/evaluate_lookup.ipynb` — Existing notebook pattern to follow for cell organization.

### New Files to Create

- `notebooks/evals/eval_input_parser.ipynb` — The evaluation notebook

### Relevant Documentation

- [LangSmith Evaluation Quickstart](https://docs.langchain.com/langsmith/evaluation-quickstart) — Dataset creation, evaluator patterns, `aevaluate()` API
- [Evaluate a Complex Agent](https://docs.langchain.com/langsmith/evaluate-complex-agent) — Final response, single step, and trajectory eval patterns
- [LLM-as-Judge Evaluator](https://docs.langchain.com/langsmith/llm-as-judge-sdk) — Structured output judge pattern
- [Reference notebook](https://github.com/langchain-ai/the-judge/blob/main/build-eval-agent/agent-eval.ipynb) — The pattern we're following (single step section)

### Patterns to Follow

**Target Function Pattern** (from reference notebook):
```python
async def run_input_parser(inputs: dict) -> dict:
    """Run the input_parser_node and return its outputs for evaluation."""
    state = {"messages": [HumanMessage(content=inputs["question"])]}
    result = input_parser_node(state)
    return {
        "action": result["last_action"],
        "items": result["pending_food_items"],
        "consumed_at": str(result.get("consumed_at")) if result.get("consumed_at") else None,
        "start_date": str(result.get("start_date")) if result.get("start_date") else None,
        "end_date": str(result.get("end_date")) if result.get("end_date") else None,
    }
```

**Evaluator Signature Pattern**:
```python
# Deterministic evaluator — returns bool
def correct_action(outputs: dict, reference_outputs: dict) -> bool:
    return outputs["action"] == reference_outputs["action"]

# Multi-score evaluator — returns dict with key and score
def amount_accuracy(outputs: dict, reference_outputs: dict) -> dict:
    return {"key": "amount_accuracy", "score": calculated_score}

# LLM-as-judge — returns bool
async def food_name_quality(inputs: dict, outputs: dict, reference_outputs: dict) -> bool:
    ...
```

**Dataset Creation Pattern** (from reference notebook):
```python
client = Client()
dataset_name = "FitPal: Input Parser"
if not client.has_dataset(dataset_name=dataset_name):
    dataset = client.create_dataset(dataset_name=dataset_name)
    client.create_examples(
        inputs=[{"question": ex["question"]} for ex in examples],
        outputs=[{k: v for k, v in ex.items() if k != "question"} for ex in examples],
        dataset_id=dataset.id,
    )
```

---

## IMPLEMENTATION PLAN

### Phase 1: Notebook Setup

Create the notebook with environment setup: imports, sys.path configuration, dotenv loading, LangSmith client initialization.

### Phase 2: Dataset Definition

Define ~15 examples as Python dicts covering all 4 action types with full reference fields. Upload to LangSmith as a dataset.

### Phase 3: Target Function

Define the function that calls `input_parser_node` with a minimal state and returns structured outputs.

### Phase 4: Evaluators

Implement 5 evaluators: 4 deterministic + 1 LLM-as-judge.

### Phase 5: Run & Display

Execute `client.aevaluate()` with all evaluators, display results.

---

## STEP-BY-STEP TASKS

### Task 1: CREATE `notebooks/evals/eval_input_parser.ipynb`

The notebook should have the following cells in order:

---

#### Cell 1 (Markdown): Title & Overview

```markdown
# Input Parser — Single Step Evaluation

Evaluates `input_parser_node` in isolation across 5 dimensions:
1. **Action Classification** — correct routing decision (deterministic)
2. **Item Count** — correct number of food items extracted (deterministic)
3. **Amount Accuracy** — gram conversion within ±20% tolerance (deterministic)
4. **Date Parsing** — correct date/time extraction (deterministic)
5. **Food Name Quality** — search-friendly normalization (LLM-as-judge)
```

---

#### Cell 2 (Code): Environment Setup

```python
import sys
import os
from pathlib import Path

# Add project root to path
project_root = str(Path.cwd().parent.parent)  # notebooks/evals/ -> project root
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv()

from langsmith import Client
from langchain_core.messages import HumanMessage

from src.agents.nodes.input_node import input_parser_node
from src.config import get_llm_for_node
```

**GOTCHA**: The notebook runs from `notebooks/evals/`. Need `parent.parent` to reach project root for imports.

**GOTCHA**: `input_parser_node` loads `prompts/input_parser.md` using `BASE_DIR` from `src.config`, which is calculated relative to `config.py`. This works regardless of notebook working directory.

---

#### Cell 3 (Markdown): Dataset Section Header

```markdown
## Dataset: FitPal Input Parser

~15 examples covering all 4 action types with full reference outputs.
```

---

#### Cell 4 (Code): Dataset Definition & Upload

Define examples as a list of dicts. Each example has:
- `question` (str) — the user input (goes into dataset `inputs`)
- `action` (str) — expected ActionType value
- `items` (list[dict]) — expected food items, each with `food_name` (str) and `amount` (float)
- `item_count` (int) — expected number of items
- `consumed_at` (str | None) — expected datetime string or null
- `start_date` (str | None) — expected date string or null
- `end_date` (str | None) — expected date string or null

**THE DATASET EXAMPLES (~15)**:

```python
examples = [
    # --- LOG_FOOD: Basic single item ---
    {
        "question": "I had 200g of chicken",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Chicken", "amount": 200.0}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- LOG_FOOD: Multi-item ---
    {
        "question": "Log a banana and 100g rice",
        "action": "LOG_FOOD",
        "items": [
            {"food_name": "Banana", "amount": 120.0},
            {"food_name": "Rice", "amount": 100.0},
        ],
        "item_count": 2,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- LOG_FOOD: No verb, just food + quantity ---
    {
        "question": "200g chicken breast",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Chicken Breast", "amount": 200.0}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- LOG_FOOD: Single word, no quantity (default serving) ---
    {
        "question": "Coffee",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Coffee", "amount": 240.0}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- LOG_FOOD: Meal decomposition ---
    {
        "question": "Pasta with cheese for lunch",
        "action": "LOG_FOOD",
        "items": [
            {"food_name": "Pasta", "amount": 200.0},
            {"food_name": "Cheese", "amount": 30.0},
        ],
        "item_count": 2,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- LOG_FOOD: Unit conversion (cups -> grams) ---
    {
        "question": "I had 1 cup of rice",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Rice", "amount": 158.0}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- LOG_FOOD: Unit conversion (slices -> grams) ---
    {
        "question": "2 slices of bread",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Bread", "amount": 60.0}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- LOG_FOOD: "protein" in text should NOT confuse with stats ---
    {
        "question": "I had a protein shake after my workout",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Protein Shake", "amount": 300.0}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- LOG_FOOD: With relative time ---
    {
        "question": "I ate 200g of chicken 2 hours ago",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Chicken", "amount": 200.0}],
        "item_count": 1,
        "consumed_at": "RELATIVE",
        "start_date": None,
        "end_date": None,
    },
    # --- LOG_FOOD: With specific date ---
    {
        "question": "I had a banana yesterday",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Banana", "amount": 120.0}],
        "item_count": 1,
        "consumed_at": "YESTERDAY_NOON",
        "start_date": None,
        "end_date": None,
    },
    # --- QUERY_FOOD_INFO ---
    {
        "question": "How much protein is in an egg?",
        "action": "QUERY_FOOD_INFO",
        "items": [],
        "item_count": 0,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- QUERY_FOOD_INFO: Could confuse with LOG_FOOD ---
    {
        "question": "How many calories does a banana have?",
        "action": "QUERY_FOOD_INFO",
        "items": [],
        "item_count": 0,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- QUERY_DAILY_STATS: Basic ---
    {
        "question": "What did I eat today?",
        "action": "QUERY_DAILY_STATS",
        "items": [],
        "item_count": 0,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- QUERY_DAILY_STATS: With date range ---
    {
        "question": "Stats for last 3 days",
        "action": "QUERY_DAILY_STATS",
        "items": [],
        "item_count": 0,
        "consumed_at": None,
        "start_date": "RELATIVE_3_DAYS_AGO",
        "end_date": "TODAY",
    },
    # --- CHITCHAT ---
    {
        "question": "Hello, how are you?",
        "action": "CHITCHAT",
        "items": [],
        "item_count": 0,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
]
```

**IMPORTANT — Date handling in the dataset**:

Dates like "yesterday" and "2 hours ago" depend on when the eval runs. The dataset stores sentinel values (`"RELATIVE"`, `"YESTERDAY_NOON"`, `"RELATIVE_3_DAYS_AGO"`, `"TODAY"`) instead of hardcoded dates. The date evaluator resolves these sentinels at eval time:

```python
from datetime import date, datetime, timedelta

def _resolve_date_sentinel(sentinel: str | None) -> str | None:
    """Convert sentinel values to actual date strings at eval time."""
    if sentinel is None:
        return None
    today = date.today()
    mapping = {
        "TODAY": str(today),
        "YESTERDAY_NOON": str(datetime.combine(today - timedelta(days=1), datetime.min.replace(hour=12).time())),
        "RELATIVE_3_DAYS_AGO": str(today - timedelta(days=3)),
    }
    if sentinel in mapping:
        return mapping[sentinel]
    if sentinel == "RELATIVE":
        return "RELATIVE"  # Special case: just check it's not None
    return sentinel
```

Upload to LangSmith:

```python
client = Client()
dataset_name = "FitPal: Input Parser"
if not client.has_dataset(dataset_name=dataset_name):
    dataset = client.create_dataset(dataset_name=dataset_name)
    client.create_examples(
        inputs=[{"question": ex["question"]} for ex in examples],
        outputs=[{k: v for k, v in ex.items() if k != "question"} for ex in examples],
        dataset_id=dataset.id,
    )
```

---

#### Cell 5 (Markdown): Target Function Section

```markdown
## Target Function

Calls `input_parser_node` directly with a minimal state dict.
```

---

#### Cell 6 (Code): Target Function

```python
async def run_input_parser(inputs: dict) -> dict:
    """Run input_parser_node and return structured outputs for evaluation."""
    state = {"messages": [HumanMessage(content=inputs["question"])]}
    result = input_parser_node(state)
    return {
        "action": result["last_action"],
        "items": result["pending_food_items"],
        "item_count": len(result["pending_food_items"]),
        "consumed_at": str(result["consumed_at"]) if result.get("consumed_at") else None,
        "start_date": str(result["start_date"]) if result.get("start_date") else None,
        "end_date": str(result["end_date"]) if result.get("end_date") else None,
    }
```

**NOTE**: `input_parser_node` is sync, but `aevaluate` needs an async target. Wrapping a sync call in an async function is fine — no event loop conflict since there's no `await` inside.

---

#### Cell 7 (Markdown): Evaluators Section

```markdown
## Evaluators

5 evaluators, each checking one dimension of the parser output.
```

---

#### Cell 8 (Code): Evaluator 1 — Action Classification

```python
def correct_action(outputs: dict, reference_outputs: dict) -> bool:
    """Check if the parser selected the correct action/route."""
    return outputs["action"] == reference_outputs["action"]
```

---

#### Cell 9 (Code): Evaluator 2 — Item Count

```python
def correct_item_count(outputs: dict, reference_outputs: dict) -> bool:
    """Check if the parser extracted the correct number of food items."""
    return outputs["item_count"] == reference_outputs["item_count"]
```

---

#### Cell 10 (Code): Evaluator 3 — Amount Accuracy

```python
def amount_accuracy(outputs: dict, reference_outputs: dict) -> dict:
    """Check if extracted amounts are within ±20% of expected values.

    Returns a score between 0.0 and 1.0 (fraction of items within tolerance).
    Skips if no items expected (non-food actions).
    """
    expected_items = reference_outputs.get("items", [])
    actual_items = outputs.get("items", [])

    if not expected_items:
        return {"key": "amount_accuracy", "score": 1.0, "comment": "No items to check"}

    if len(actual_items) != len(expected_items):
        return {"key": "amount_accuracy", "score": 0.0, "comment": "Item count mismatch, cannot compare amounts"}

    # Sort both lists by food_name for alignment
    expected_sorted = sorted(expected_items, key=lambda x: x["food_name"].lower())
    actual_sorted = sorted(actual_items, key=lambda x: x["food_name"].lower())

    within_tolerance = 0
    details = []
    for exp, act in zip(expected_sorted, actual_sorted):
        exp_amount = exp["amount"]
        act_amount = act["amount"]
        tolerance = exp_amount * 0.20
        is_close = abs(act_amount - exp_amount) <= tolerance
        if is_close:
            within_tolerance += 1
        details.append(f"{act.get('food_name', '?')}: {act_amount}g vs {exp_amount}g ({'OK' if is_close else 'FAIL'})")

    score = within_tolerance / len(expected_items)
    return {"key": "amount_accuracy", "score": score, "comment": "; ".join(details)}
```

---

#### Cell 11 (Code): Evaluator 4 — Date Parsing

```python
from datetime import date, datetime, timedelta

def _resolve_date_sentinel(sentinel: str | None) -> str | None:
    """Convert sentinel values to actual date strings at eval time."""
    if sentinel is None:
        return None
    today = date.today()
    mapping = {
        "TODAY": str(today),
        "YESTERDAY_NOON": str(datetime.combine(today - timedelta(days=1), datetime.min.replace(hour=12).time())),
        "RELATIVE_3_DAYS_AGO": str(today - timedelta(days=3)),
    }
    if sentinel in mapping:
        return mapping[sentinel]
    if sentinel == "RELATIVE":
        return "RELATIVE"
    return sentinel

def correct_dates(outputs: dict, reference_outputs: dict) -> bool:
    """Check if date/time extraction matches expected values.

    Handles sentinel values for relative dates.
    For 'RELATIVE' consumed_at: just checks it's not None (exact time depends on when eval runs).
    For specific dates: checks date portion matches.
    """
    # Check consumed_at
    expected_consumed = _resolve_date_sentinel(reference_outputs.get("consumed_at"))
    actual_consumed = outputs.get("consumed_at")

    if expected_consumed == "RELATIVE":
        # Just verify it's not None — exact time depends on eval runtime
        if actual_consumed is None:
            return False
    elif expected_consumed is not None:
        if actual_consumed is None:
            return False
        # Compare date portion only (time may vary slightly)
        if expected_consumed[:10] != actual_consumed[:10]:
            return False
    else:
        if actual_consumed is not None:
            return False

    # Check start_date
    expected_start = _resolve_date_sentinel(reference_outputs.get("start_date"))
    actual_start = outputs.get("start_date")
    if expected_start != actual_start:
        # For date ranges, compare date portion
        if expected_start is not None and actual_start is not None:
            if expected_start[:10] != actual_start[:10]:
                return False
        elif expected_start != actual_start:
            return False

    # Check end_date
    expected_end = _resolve_date_sentinel(reference_outputs.get("end_date"))
    actual_end = outputs.get("end_date")
    if expected_end != actual_end:
        if expected_end is not None and actual_end is not None:
            if expected_end[:10] != actual_end[:10]:
                return False
        elif expected_end != actual_end:
            return False

    return True
```

---

#### Cell 12 (Code): Evaluator 5 — Food Name Quality (LLM-as-Judge)

```python
from langchain.chat_models import init_chat_model
from typing_extensions import Annotated, TypedDict

class NameGrade(TypedDict):
    """Grade for food name normalization quality."""
    reasoning: Annotated[str, ..., "Step-by-step reasoning for the grade."]
    is_acceptable: Annotated[bool, ..., "True if the name is a reasonable search-friendly normalization."]

judge_instructions = """You are evaluating whether a food name has been properly normalized for database search.

Rules:
- The name should be generic and search-friendly (e.g., "Apple" not "Small sour green apple")
- Minor variations are acceptable ("Chicken" vs "Chicken Breast" — both valid)
- The name must still refer to the same food as the original text
- Compound dishes should be decomposed ("Pasta with cheese" -> "Pasta" and "Cheese" separately)

Grade as acceptable if a nutrition database search for this name would reasonably find the correct food."""

judge_llm = init_chat_model("gpt-4o-mini", temperature=0).with_structured_output(
    NameGrade, method="json_schema"
)

async def food_name_quality(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """LLM-as-judge: evaluate if food names are reasonable normalizations.

    Skips if no items expected (non-food actions). Returns score 0.0-1.0
    (fraction of names graded acceptable).
    """
    expected_items = reference_outputs.get("items", [])
    actual_items = outputs.get("items", [])

    if not expected_items:
        return {"key": "food_name_quality", "score": 1.0, "comment": "No items to check"}

    if not actual_items:
        return {"key": "food_name_quality", "score": 0.0, "comment": "No items produced"}

    acceptable_count = 0
    details = []

    for act in actual_items:
        msg = f"""Original user input: "{inputs['question']}"
Extracted food name: "{act.get('food_name', '')}"

Is this a reasonable, search-friendly normalization?"""

        grade = await judge_llm.ainvoke([
            {"role": "system", "content": judge_instructions},
            {"role": "user", "content": msg},
        ])

        if grade["is_acceptable"]:
            acceptable_count += 1
        details.append(f"{act.get('food_name', '?')}: {'OK' if grade['is_acceptable'] else 'FAIL'} — {grade['reasoning'][:80]}")

    score = acceptable_count / len(actual_items)
    return {"key": "food_name_quality", "score": score, "comment": "; ".join(details)}
```

---

#### Cell 13 (Markdown): Run Evaluation Section

```markdown
## Run Evaluation

Execute all evaluators against the dataset and display results.
```

---

#### Cell 14 (Code): Run Evaluation

```python
experiment_results = await client.aevaluate(
    run_input_parser,
    data=dataset_name,
    evaluators=[correct_action, correct_item_count, amount_accuracy, correct_dates, food_name_quality],
    experiment_prefix="fitpal-input-parser",
    max_concurrency=4,
)
experiment_results.to_pandas()
```

---

#### Cell 15 (Markdown): Analysis / Notes

```markdown
## Notes

- Re-run this notebook after changing the input parser prompt or switching LLM models
- Compare experiments in LangSmith UI: Datasets & Testing → FitPal: Input Parser
- To add more examples, update the `examples` list and delete/recreate the dataset
- Amount tolerance is ±20% — adjust in `amount_accuracy` if too strict/lenient
```

---

## TESTING STRATEGY

### Manual Validation

This is a notebook, not a pytest test. Validation is:

1. Run all cells top to bottom — no errors
2. Check LangSmith UI shows the dataset and experiment
3. Review per-example scores in the pandas output
4. Click into failing examples in LangSmith to see full traces

### Smoke Test

Before running the full eval, test the target function on one example:

```python
# Quick smoke test (add as optional cell)
test_result = await run_input_parser({"question": "I had 200g of chicken"})
print(test_result)
# Should show: action=LOG_FOOD, items=[{food_name: Chicken, amount: 200}], dates=None
```

---

## VALIDATION COMMANDS

### Level 1: Notebook Runs Without Errors

```bash
cd notebooks/evals && uv run jupyter nbconvert --to notebook --execute eval_input_parser.ipynb --output /dev/null
```

### Level 2: Dataset Exists in LangSmith

After running — check LangSmith UI → Datasets & Testing → "FitPal: Input Parser" exists with 15 examples.

### Level 3: Experiment Results

After running — check LangSmith UI → experiment shows 5 evaluator scores per example.

---

## ACCEPTANCE CRITERIA

- [ ] `notebooks/evals/eval_input_parser.ipynb` exists and runs without errors
- [ ] Dataset "FitPal: Input Parser" created in LangSmith with ~15 examples
- [ ] All 4 action types covered (LOG_FOOD, QUERY_FOOD_INFO, QUERY_DAILY_STATS, CHITCHAT)
- [ ] 5 evaluators run on every example and produce scores
- [ ] Evaluator 1 (action): deterministic `==` comparison
- [ ] Evaluator 2 (item count): deterministic `==` comparison
- [ ] Evaluator 3 (amount): ±20% tolerance, returns 0.0-1.0 score
- [ ] Evaluator 4 (dates): handles sentinel values for relative dates
- [ ] Evaluator 5 (food name): LLM-as-judge with structured output
- [ ] Results visible in LangSmith UI as an experiment
- [ ] `experiment_results.to_pandas()` displays inline in notebook

---

## COMPLETION CHECKLIST

- [ ] Notebook created at `notebooks/evals/eval_input_parser.ipynb`
- [ ] All cells run top-to-bottom without errors
- [ ] Dataset uploaded to LangSmith
- [ ] Experiment results visible in LangSmith
- [ ] Pandas DataFrame displays in notebook output

---

## NOTES

- **Why notebook over pytest**: Evals are exploratory and interactive. You tweak examples, re-run cells, inspect results. pytest is for CI pass/fail; evals are for quality measurement.
- **Why node-level over raw LLM**: Tests the full pipeline (prompt loading, system time injection, structured output parsing, state update logic), not just the LLM in isolation. Produces richer LangSmith traces.
- **Date sentinels**: Hardcoding dates would make examples stale. Sentinel values resolve at eval time so "yesterday" always means yesterday.
- **Amount tolerance (±20%)**: Default serving sizes vary by source. 120g vs 140g for a banana are both reasonable. Adjust if needed.
- **LLM-as-judge cost**: Only evaluator 5 makes LLM calls. With 15 examples × ~1.5 items avg = ~22 judge calls using gpt-4o-mini. Cheap.
- **`QUERY_FOOD_INFO` items**: The prompt says to return empty items for QUERY_FOOD_INFO. This is by design — the food_search_node handles the lookup separately. If this changes in the future, update both the prompt and the dataset.
