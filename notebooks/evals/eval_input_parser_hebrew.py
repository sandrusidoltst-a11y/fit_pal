"""Input Parser (Hebrew) — single-step evaluation.

Runs `input_parser_node` against the "Input Parser Hebrew" LangSmith dataset
across 5 dimensions (action, item count, amount accuracy, dates, food-name
quality). Results land in LangSmith under the experiment prefix derived from
the effective model — swap `LLM_MODEL_NAME` in `.env` (or set a `model` in
`NODE_CONFIGS["input_node"]`) and rerun; experiments auto-label correctly.

Run: `uv run python notebooks/evals/eval_input_parser_hebrew.py`
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from langsmith import Client
from typing_extensions import TypedDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from src.agents.nodes.input_node import input_parser_node  # noqa: E402
from src.config import GLOBAL_MODEL, NODE_CONFIGS  # noqa: E402

DATASET_ID = "175cb9ae-e063-466c-a79a-c71db1d94ca2"
DATASET_NAME = "Input Parser Hebrew"

EXAMPLES: list[dict] = [
    # --- LOG_FOOD: Basic single item ---
    {
        "question": "אכלתי 200 גרם עוף",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Chicken", "amount": 200.0}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- LOG_FOOD: Multi-item ---
    {
        "question": "תרשום בננה ו-100 גרם אורז",
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
        "question": "200 גרם חזה עוף",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Chicken Breast", "amount": 200.0}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- LOG_FOOD: Single word, no quantity (default serving) ---
    {
        "question": "קפה",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Coffee", "amount": 240.0}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- LOG_FOOD: Meal decomposition ---
    {
        "question": "פסטה עם גבינה לצהריים",
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
        "question": "אכלתי כוס אורז",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Rice", "amount": 158.0}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- LOG_FOOD: Unit conversion (slices -> grams) ---
    {
        "question": "2 פרוסות לחם",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Bread", "amount": 60.0}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- LOG_FOOD: "חלבון" in text should NOT confuse with stats ---
    {
        "question": "שתיתי שייק חלבון אחרי אימון",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Protein Shake", "amount": 300.0}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- LOG_FOOD: With relative time ---
    {
        "question": "אכלתי 200 גרם עוף לפני שעתיים",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Chicken", "amount": 200.0}],
        "item_count": 1,
        "consumed_at": "RELATIVE",
        "start_date": None,
        "end_date": None,
    },
    # --- LOG_FOOD: With specific date ---
    {
        "question": "אכלתי בננה אתמול",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Banana", "amount": 120.0}],
        "item_count": 1,
        "consumed_at": "YESTERDAY_NOON",
        "start_date": None,
        "end_date": None,
    },
    # --- QUERY_FOOD_INFO ---
    {
        "question": "כמה חלבון יש בביצה?",
        "action": "QUERY_FOOD_INFO",
        "items": [],
        "item_count": 0,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- QUERY_FOOD_INFO: Could confuse with LOG_FOOD ---
    {
        "question": "כמה קלוריות יש בבננה?",
        "action": "QUERY_FOOD_INFO",
        "items": [],
        "item_count": 0,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- QUERY_DAILY_STATS: Basic ---
    {
        "question": "מה אכלתי היום?",
        "action": "QUERY_DAILY_STATS",
        "items": [],
        "item_count": 0,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- QUERY_DAILY_STATS: With date range (3 days) ---
    {
        "question": "סטטיסטיקות של 3 ימים אחרונים",
        "action": "QUERY_DAILY_STATS",
        "items": [],
        "item_count": 0,
        "consumed_at": None,
        "start_date": "RELATIVE_3_DAYS_AGO",
        "end_date": "TODAY",
    },
    # --- CHITCHAT ---
    {
        "question": "היי מה נשמע?",
        "action": "CHITCHAT",
        "items": [],
        "item_count": 0,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- QUERY_DAILY_STATS: Weekly range ---
    {
        "question": "מה אכלתי בשבוע האחרון",
        "action": "QUERY_DAILY_STATS",
        "items": [],
        "item_count": 0,
        "consumed_at": None,
        "start_date": "RELATIVE_7_DAYS_AGO",
        "end_date": "TODAY",
    },
    # --- QUERY_DAILY_STATS: Specific macro question over range ---
    {
        "question": "כמה גרם חלבון אכלתי בממוצע בשבוע האחרון",
        "action": "QUERY_DAILY_STATS",
        "items": [],
        "item_count": 0,
        "consumed_at": None,
        "start_date": "RELATIVE_7_DAYS_AGO",
        "end_date": "TODAY",
    },
    # ==========================================================================
    # Hebrew quantifier stress (audit 2026-04-17, Fix #7)
    # Word-form quantifiers ("שתי", "שלוש", "חמש") drop or get misread as grams.
    # ==========================================================================
    # --- A1: Exact F3 T6 reproduction — "two pitas" returned as one in prod ---
    {
        "question": "שתי פיתות",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Pita", "amount": 240.0}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- A2: Rice cakes — quantifier dropped, treated as grams (5g instead of ~40g) ---
    {
        "question": "חמש פריכיות אורז",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Rice Cake", "amount": 40.0}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- A3: Cheese slices — wrong serving weight (prod returned 30g for 2 slices) ---
    {
        "question": "שתי פרוסות גבינה",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Cheese", "amount": 50.0}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- A4: Food-name mistranslation — protein pudding → "Protein Bar" in prod ---
    {
        "question": "מעדן חלבון",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Protein Pudding", "amount": 130.0}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- B1: Three eggs, feminine form ---
    {
        "question": "שלוש ביצים",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Egg", "amount": 150.0}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- B2: Four bread slices — direct A/B vs. existing digit-form "2 פרוסות לחם" ---
    {
        "question": "ארבע פרוסות לחם",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Bread", "amount": 120.0}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- B3: Half a banana — fractional quantifier ---
    {
        "question": "חצי בננה",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Banana", "amount": 60.0}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- B4: Half cup of rice — fractional + unit conversion ---
    {
        "question": "חצי כוס אורז",
        "action": "LOG_FOOD",
        "items": [{"food_name": "Rice", "amount": 79.0}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- C1: Multi-item with word quantifiers on both ---
    {
        "question": "שתי פיתות ושלוש ביצים",
        "action": "LOG_FOOD",
        "items": [
            {"food_name": "Pita", "amount": 240.0},
            {"food_name": "Egg", "amount": 150.0},
        ],
        "item_count": 2,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- C2: Mixed word-quantifier + no-quantifier compound ---
    {
        "question": "שתי פרוסות גבינה עם מעדן חלבון",
        "action": "LOG_FOOD",
        "items": [
            {"food_name": "Cheese", "amount": 50.0},
            {"food_name": "Protein Pudding", "amount": 130.0},
        ],
        "item_count": 2,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- D1: Control — word quantifier inside a QUERY, must NOT route to LOG_FOOD ---
    {
        "question": "כמה חלבון יש בשלוש ביצים?",
        "action": "QUERY_FOOD_INFO",
        "items": [],
        "item_count": 0,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
]


def effective_input_node_model() -> str:
    """Mirror the resolution inside `get_llm_for_node("input_node")`."""
    node_config = NODE_CONFIGS.get("input_node", NODE_CONFIGS.get("default", {}))
    return node_config.get("model", GLOBAL_MODEL)


def experiment_prefix() -> str:
    model_slug = effective_input_node_model().replace("/", "-")
    return f"input-parser-hebrew-{model_slug}"


async def run_input_parser(inputs: dict) -> dict:
    """Run input_parser_node and return structured outputs for evaluation."""
    state = {"messages": [HumanMessage(content=inputs["question"])]}
    result = await input_parser_node(state)
    return {
        "action": result["last_action"],
        "items": result["pending_food_items"],
        "item_count": len(result["pending_food_items"]),
        "consumed_at": str(result["consumed_at"]) if result.get("consumed_at") else None,
        "start_date": str(result["start_date"]) if result.get("start_date") else None,
        "end_date": str(result["end_date"]) if result.get("end_date") else None,
    }


def correct_action(outputs: dict, reference_outputs: dict) -> bool:
    """Check if the parser selected the correct action/route."""
    return outputs["action"] == reference_outputs["action"]


def correct_item_count(outputs: dict, reference_outputs: dict) -> bool:
    """Check if the parser extracted the correct number of food items."""
    return outputs["item_count"] == reference_outputs["item_count"]


def amount_accuracy(outputs: dict, reference_outputs: dict) -> dict:
    """Fraction of items whose gram amount is within ±20% of expected."""
    expected_items = reference_outputs.get("items", [])
    actual_items = outputs.get("items", [])

    if not expected_items:
        return {"key": "amount_accuracy", "score": 1.0, "comment": "No items to check"}

    if len(actual_items) != len(expected_items):
        return {
            "key": "amount_accuracy",
            "score": 0.0,
            "comment": f"Item count mismatch: got {len(actual_items)}, expected {len(expected_items)}",
        }

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
        details.append(
            f"{act.get('food_name', '?')}: {act_amount}g vs {exp_amount}g"
            f" {'(OK)' if is_close else '(FAIL)'}"
        )

    score = within_tolerance / len(expected_items)
    return {"key": "amount_accuracy", "score": score, "comment": "; ".join(details)}


def _resolve_date_sentinel(sentinel: str | None) -> str | None:
    """Convert sentinel values to actual date strings at eval time."""
    if sentinel is None:
        return None
    today = date.today()
    mapping = {
        "TODAY": str(today),
        "YESTERDAY": str(today - timedelta(days=1)),
        "YESTERDAY_NOON": str(
            datetime.combine(
                today - timedelta(days=1),
                datetime.min.replace(hour=12).time(),
            )
        ),
        "RELATIVE_3_DAYS_AGO": str(today - timedelta(days=3)),
        "RELATIVE_7_DAYS_AGO": str(today - timedelta(days=7)),
    }
    if sentinel in mapping:
        return mapping[sentinel]
    if sentinel == "RELATIVE":
        return "RELATIVE"
    return sentinel


def _dates_equivalent(expected: str | None, actual: str | None) -> bool:
    """Compare date values, treating null and today as equivalent."""
    if expected is None and actual is None:
        return True
    if expected is not None and actual is not None:
        return expected[:10] == actual[:10]
    today_str = str(date.today())
    if expected is None and actual is not None:
        return actual[:10] == today_str
    if expected is not None and actual is None:
        return expected[:10] == today_str
    return False


def correct_dates(outputs: dict, reference_outputs: dict) -> bool:
    """Check if date/time extraction matches expected values."""
    expected_consumed = _resolve_date_sentinel(reference_outputs.get("consumed_at"))
    actual_consumed = outputs.get("consumed_at")

    if expected_consumed == "RELATIVE":
        if actual_consumed is None:
            return False
    elif expected_consumed is not None:
        if actual_consumed is None:
            return False
        if expected_consumed[:10] != actual_consumed[:10]:
            return False
    else:
        if actual_consumed is not None:
            return False

    expected_start = _resolve_date_sentinel(reference_outputs.get("start_date"))
    actual_start = outputs.get("start_date")
    if not _dates_equivalent(expected_start, actual_start):
        return False

    expected_end = _resolve_date_sentinel(reference_outputs.get("end_date"))
    actual_end = outputs.get("end_date")
    if not _dates_equivalent(expected_end, actual_end):
        return False

    return True


class NameGrade(TypedDict):
    """Grade for food name normalization quality."""

    reasoning: Annotated[str, ..., "Step-by-step reasoning for the grade."]
    is_acceptable: Annotated[
        bool, ..., "True if the name is a reasonable search-friendly normalization."
    ]


JUDGE_INSTRUCTIONS = """You are evaluating whether a food name has been properly normalized for database search.

The original user input is in Hebrew, but the extracted food name should be in English (for database lookup).

Rules:
- The name should be generic and search-friendly (e.g., "Apple" not "Small sour green apple")
- Minor variations are acceptable ("Chicken" vs "Chicken Breast" - both valid)
- The name must still refer to the same food as the original Hebrew text
- Compound dishes should be decomposed (Hebrew for "pasta with cheese" -> "Pasta" and "Cheese" separately)
- Individual ingredients from decomposed dishes are valid on their own
- Common food product names are acceptable even if multi-word ("Protein Shake", "Peanut Butter")
- Do NOT penalize names that are already standard food category names
- The name MUST be in English, not Hebrew

Grade as acceptable if a nutrition database search for this name would reasonably find the correct food."""

_judge_llm = None


def _get_judge_llm():
    """Build the LLM-as-judge lazily. Structured-output schema construction
    is eager and expensive; deferring keeps module import fast and avoids
    triggering the pydantic/TypedDict schema path when the eval isn't run."""
    global _judge_llm
    if _judge_llm is None:
        _judge_llm = init_chat_model("gpt-4o", temperature=0).with_structured_output(
            NameGrade, method="json_schema"
        )
    return _judge_llm


async def food_name_quality(
    inputs: dict, outputs: dict, reference_outputs: dict
) -> dict:
    """LLM-as-judge: fraction of extracted food names graded acceptable."""
    expected_items = reference_outputs.get("items", [])
    actual_items = outputs.get("items", [])

    if not expected_items:
        return {"key": "food_name_quality", "score": 1.0, "comment": "No items to check"}

    if not actual_items:
        return {"key": "food_name_quality", "score": 0.0, "comment": "No items produced"}

    acceptable_count = 0
    details = []

    for act in actual_items:
        msg = (
            f'Original user input (Hebrew): "{inputs["question"]}"\n'
            f'Extracted food name: "{act.get("food_name", "")}"\n'
            f"\nIs this a reasonable, search-friendly English normalization of the Hebrew input?"
        )

        grade = await _get_judge_llm().ainvoke(
            [
                {"role": "system", "content": JUDGE_INSTRUCTIONS},
                {"role": "user", "content": msg},
            ]
        )

        if grade["is_acceptable"]:
            acceptable_count += 1
        details.append(
            f"{act.get('food_name', '?')}: "
            f"{'OK' if grade['is_acceptable'] else 'FAIL'} - "
            f"{grade['reasoning'][:80]}"
        )

    score = acceptable_count / len(actual_items)
    return {"key": "food_name_quality", "score": score, "comment": "; ".join(details)}


async def sync_dataset(client: Client) -> None:
    """Idempotent upload: add any EXAMPLES whose question is not yet in LangSmith.
    Never deletes or mutates existing examples — the code is the append-only
    source of truth; to retire an example, remove it from EXAMPLES AND from
    the LangSmith UI."""
    existing = list(client.list_examples(dataset_id=DATASET_ID))
    existing_questions = {ex.inputs.get("question") for ex in existing}
    new_examples = [ex for ex in EXAMPLES if ex["question"] not in existing_questions]
    if not new_examples:
        print(f"Dataset '{DATASET_NAME}' is up to date ({len(existing)} examples)")
        return
    client.create_examples(
        inputs=[{"question": ex["question"]} for ex in new_examples],
        outputs=[{k: v for k, v in ex.items() if k != "question"} for ex in new_examples],
        dataset_id=DATASET_ID,
    )
    print(
        f"Uploaded {len(new_examples)} new examples to '{DATASET_NAME}' "
        f"(total now {len(existing) + len(new_examples)})"
    )


async def main() -> None:
    client = Client()
    await sync_dataset(client)

    prefix = experiment_prefix()
    print(f"Running experiment: {prefix}")

    experiment_results = await client.aevaluate(
        run_input_parser,
        data=DATASET_ID,
        evaluators=[
            correct_action,
            correct_item_count,
            amount_accuracy,
            correct_dates,
            food_name_quality,
        ],
        experiment_prefix=prefix,
        max_concurrency=4,
    )
    print(experiment_results.to_pandas())


if __name__ == "__main__":
    asyncio.run(main())
