"""Input Parser (Hebrew) — single-step evaluation.

Runs `input_parser_node` against the "Input Parser Hebrew" LangSmith dataset
across 5 dimensions (action, item count, serving correctness, dates, food-name
quality). Expectations use the current `count` + `unit` schema and accept
bilingual (Hebrew OR English) food names — the catalog search is bilingual.

Results land in LangSmith under an experiment prefix derived from the effective
model — swap `LLM_MODEL_NAME` in `.env` (or set a `model` in
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
        "items": [{"food_name": "עוף", "count": 200, "unit": "g"}],
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
            {"food_name": "בננה", "count": 120, "unit": "g"},
            {"food_name": "אורז", "count": 100, "unit": "g"},
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
        "items": [{"food_name": "חזה עוף", "count": 200, "unit": "g"}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- LOG_FOOD: Single word, no quantity (default serving) ---
    {
        "question": "קפה",
        "action": "LOG_FOOD",
        "items": [{"food_name": "קפה", "count": 240, "unit": "g"}],
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
            {"food_name": "פסטה", "count": 200, "unit": "g"},
            {"food_name": "גבינה", "count": 30, "unit": "g"},
        ],
        "item_count": 2,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- LOG_FOOD: Cup -> grams (rice not in unit-bucket table, gram-native) ---
    {
        "question": "אכלתי כוס אורז",
        "action": "LOG_FOOD",
        "items": [{"food_name": "אורז", "count": 158, "unit": "g"}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- LOG_FOOD: Bread is slice-bucket, keep as slices ---
    {
        "question": "2 פרוסות לחם",
        "action": "LOG_FOOD",
        "items": [{"food_name": "לחם", "count": 2, "unit": "slice"}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- LOG_FOOD: "חלבון" in text should NOT confuse with stats ---
    {
        "question": "שתיתי שייק חלבון אחרי אימון",
        "action": "LOG_FOOD",
        "items": [{"food_name": "שייק חלבון", "count": 300, "unit": "g"}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- LOG_FOOD: With relative time ---
    {
        "question": "אכלתי 200 גרם עוף לפני שעתיים",
        "action": "LOG_FOOD",
        "items": [{"food_name": "עוף", "count": 200, "unit": "g"}],
        "item_count": 1,
        "consumed_at": "RELATIVE",
        "start_date": None,
        "end_date": None,
        "category": "temporal",
    },
    # --- LOG_FOOD: With specific date ---
    {
        "question": "אכלתי בננה אתמול",
        "action": "LOG_FOOD",
        "items": [{"food_name": "בננה", "count": 120, "unit": "g"}],
        "item_count": 1,
        "consumed_at": "YESTERDAY_NOON",
        "start_date": None,
        "end_date": None,
        "category": "temporal",
    },
    # ==========================================================================
    # Temporal handling — past-day LOG_FOOD framing variants (audit 2026-04-30)
    # Bug repro: "תוסיף לאתמול" (add to yesterday) produced action=LOG_FOOD with
    # start_date/end_date=yesterday and consumed_at=null. Schema confusion —
    # *_date are query-range fields, consumed_at is the write timestamp.
    # Trace: 019dd286 (Dolev, 2026-04-28).
    # ==========================================================================
    # --- T1: Bug repro — "add to yesterday" with multiple items ---
    {
        "question": "תוסיף לאתמול עוד פיתה ושתי פרוסות גבינה",
        "action": "LOG_FOOD",
        "items": [
            {"food_name": "פיתה", "count": 1, "unit": "piece"},
            {"food_name": "גבינה צהובה", "count": 2, "unit": "slice"},
        ],
        "item_count": 2,
        "consumed_at": "YESTERDAY_NOON",
        "start_date": None,
        "end_date": None,
        "category": "temporal",
    },
    # --- T2: "add to yesterday" — explicit grams to keep counts deterministic ---
    {
        "question": "תוסיף לאתמול 100 גרם פסטרמה",
        "action": "LOG_FOOD",
        "items": [{"food_name": "פסטרמה", "count": 100, "unit": "g"}],
        "item_count": 1,
        "consumed_at": "YESTERDAY_NOON",
        "start_date": None,
        "end_date": None,
        "category": "temporal",
    },
    # --- T3: "register on yesterday" — different verb, same intent ---
    {
        "question": "תרשום על אתמול 200 גרם אורז",
        "action": "LOG_FOOD",
        "items": [{"food_name": "אורז", "count": 200, "unit": "g"}],
        "item_count": 1,
        "consumed_at": "YESTERDAY_NOON",
        "start_date": None,
        "end_date": None,
        "category": "temporal",
    },
    # --- T4: "I forgot to log yesterday" — past-tense reframe ---
    {
        "question": "שכחתי לרשום אתמול 200 גרם חזה עוף",
        "action": "LOG_FOOD",
        "items": [{"food_name": "חזה עוף", "count": 200, "unit": "g"}],
        "item_count": 1,
        "consumed_at": "YESTERDAY_NOON",
        "start_date": None,
        "end_date": None,
        "category": "temporal",
    },
    # --- T5: Temporal-first phrasing ---
    {
        "question": "אתמול בערב אכלתי 150 גרם אורז",
        "action": "LOG_FOOD",
        "items": [{"food_name": "אורז", "count": 150, "unit": "g"}],
        "item_count": 1,
        "consumed_at": "YESTERDAY_NOON",
        "start_date": None,
        "end_date": None,
        "category": "temporal",
    },
    # --- T6: Control — past-day question (NOT a write) → CHITCHAT or QUERY ---
    {
        "question": "אפשר להוסיף משהו על אתמול?",
        "action": "CHITCHAT",
        "items": [],
        "item_count": 0,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
        "category": "temporal",
    },
    # --- T7: Explicit time + yesterday — should set consumed_at to yesterday@21:00 ---
    {
        "question": "אכלתי אתמול בשעה 21:00 שתי לחמניות",
        "action": "LOG_FOOD",
        "items": [{"food_name": "לחמנייה", "count": 2, "unit": "piece"}],
        "item_count": 1,
        "consumed_at": "YESTERDAY",
        "start_date": None,
        "end_date": None,
        "category": "temporal",
    },
    # --- QUERY_FOOD_INFO: produces items (same extraction as LOG_FOOD) ---
    {
        "question": "כמה חלבון יש בביצה?",
        "action": "QUERY_FOOD_INFO",
        "items": [{"food_name": "ביצה", "count": 100, "unit": "g"}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- QUERY_FOOD_INFO: banana lookup (whole fruit default = 120g) ---
    {
        "question": "כמה קלוריות יש בבננה?",
        "action": "QUERY_FOOD_INFO",
        "items": [{"food_name": "בננה", "count": 120, "unit": "g"}],
        "item_count": 1,
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
        "category": "temporal",
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
        "category": "temporal",
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
        "category": "temporal",
    },
    # ==========================================================================
    # Hebrew quantifier stress (audit 2026-04-17, Fix #7)
    # Word-form quantifiers ("שתי", "שלוש", "חמש") drop or get misread as grams.
    # ==========================================================================
    # --- A1: Exact F3 T6 reproduction — pita is piece-bucket ---
    {
        "question": "שתי פיתות",
        "action": "LOG_FOOD",
        "items": [{"food_name": "פיתה", "count": 2, "unit": "piece"}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- A2: Rice cakes — piece-bucket ---
    {
        "question": "חמש פריכיות אורז",
        "action": "LOG_FOOD",
        "items": [{"food_name": "פריכיות אורז", "count": 5, "unit": "piece"}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- A3: Cheese slices — slice-bucket ---
    {
        "question": "שתי פרוסות גבינה",
        "action": "LOG_FOOD",
        "items": [{"food_name": "גבינה צהובה", "count": 2, "unit": "slice"}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- A4: Protein pudding — piece-bucket but no quantity → grams default (step 2.4) ---
    {
        "question": "מעדן חלבון",
        "action": "LOG_FOOD",
        "items": [{"food_name": "מעדן חלבון", "count": 130, "unit": "g"}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- B1: Three eggs, feminine form — piece-bucket ---
    {
        "question": "שלוש ביצים",
        "action": "LOG_FOOD",
        "items": [{"food_name": "ביצה", "count": 3, "unit": "piece"}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- B2: Four bread slices — slice-bucket ---
    {
        "question": "ארבע פרוסות לחם",
        "action": "LOG_FOOD",
        "items": [{"food_name": "לחם", "count": 4, "unit": "slice"}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- B3: Half a banana — piece-bucket fractional ---
    {
        "question": "חצי בננה",
        "action": "LOG_FOOD",
        "items": [{"food_name": "בננה", "count": 0.5, "unit": "piece"}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- B4: Half cup of rice — rice NOT in table, convert to grams ---
    {
        "question": "חצי כוס אורז",
        "action": "LOG_FOOD",
        "items": [{"food_name": "אורז", "count": 79, "unit": "g"}],
        "item_count": 1,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- C1: Multi-item with word quantifiers on both (both piece-bucket) ---
    {
        "question": "שתי פיתות ושלוש ביצים",
        "action": "LOG_FOOD",
        "items": [
            {"food_name": "פיתה", "count": 2, "unit": "piece"},
            {"food_name": "ביצה", "count": 3, "unit": "piece"},
        ],
        "item_count": 2,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- C2: Mixed slice-bucket + no-quantifier compound (pudding → grams default) ---
    {
        "question": "שתי פרוסות גבינה עם מעדן חלבון",
        "action": "LOG_FOOD",
        "items": [
            {"food_name": "גבינה צהובה", "count": 2, "unit": "slice"},
            {"food_name": "מעדן חלבון", "count": 130, "unit": "g"},
        ],
        "item_count": 2,
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
    },
    # --- D1: Control — word quantifier inside a QUERY. Produces items per prompt. ---
    {
        "question": "כמה חלבון יש בשלוש ביצים?",
        "action": "QUERY_FOOD_INFO",
        "items": [{"food_name": "ביצה", "count": 3, "unit": "piece"}],
        "item_count": 1,
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
    """Run input_parser_node and return structured outputs for evaluation.

    Post-discriminated-action-state-refactor: dates live in per-action
    sub-states (``log_food`` and ``query_stats``), not flat fields.
    """
    state = {"messages": [HumanMessage(content=inputs["question"])]}
    result = await input_parser_node(state)
    log_food = result.get("log_food") or {}
    query_stats = result.get("query_stats") or {}
    return {
        "action": result["user_intent"],
        "items": result["pending_food_items"],
        "item_count": len(result["pending_food_items"]),
        "consumed_at": str(log_food["consumed_at"]) if log_food.get("consumed_at") else None,
        "target_date": str(query_stats["target_date"]) if query_stats.get("target_date") else None,
        "start_date": str(query_stats["start_date"]) if query_stats.get("start_date") else None,
        "end_date": str(query_stats["end_date"]) if query_stats.get("end_date") else None,
    }


def correct_action(outputs: dict, reference_outputs: dict) -> bool:
    """Check if the parser selected the correct action/route."""
    return outputs["action"] == reference_outputs["action"]


def correct_item_count(outputs: dict, reference_outputs: dict) -> bool:
    """Check if the parser extracted the correct number of food items."""
    return outputs["item_count"] == reference_outputs["item_count"]


def correct_serving(outputs: dict, reference_outputs: dict) -> dict:
    """Fraction of items with correct unit AND count within ±20% of expected.

    Pairs by emission order (index), so names in either Hebrew or English
    are accepted — name quality is graded separately by ``food_name_quality``.
    """
    expected_items = reference_outputs.get("items", [])
    actual_items = outputs.get("items", [])

    if not expected_items:
        return {"key": "correct_serving", "score": 1.0, "comment": "No items to check"}

    if len(actual_items) != len(expected_items):
        return {
            "key": "correct_serving",
            "score": 0.0,
            "comment": f"Item count mismatch: got {len(actual_items)}, expected {len(expected_items)}",
        }

    correct = 0
    details = []
    for exp, act in zip(expected_items, actual_items):
        exp_count = float(exp["count"])
        act_count = float(act.get("count", 0))
        exp_unit = exp["unit"]
        act_unit = act.get("unit", "")
        unit_ok = exp_unit == act_unit
        tolerance = max(exp_count * 0.20, 0.01)
        count_ok = abs(act_count - exp_count) <= tolerance
        is_ok = unit_ok and count_ok
        if is_ok:
            correct += 1
        details.append(
            f"{act.get('food_name', '?')}: "
            f"{act_count}{act_unit} vs {exp_count}{exp_unit} "
            f"{'(OK)' if is_ok else '(FAIL' + ('' if unit_ok else ' unit') + ('' if count_ok else ' count') + ')'}"
        )

    score = correct / len(expected_items)
    return {"key": "correct_serving", "score": score, "comment": "; ".join(details)}


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


def no_query_dates_on_log_food(outputs: dict, reference_outputs: dict) -> bool:
    """When parser predicts LOG_FOOD, start_date/end_date must be null.

    Catches the schema confusion seen in trace 019dd286 (2026-04-28): "תוסיף
    לאתמול ..." was parsed as LOG_FOOD with start_date/end_date=yesterday and
    consumed_at=null — the model populated query-range fields on a write intent.
    """
    if outputs.get("action") != "LOG_FOOD":
        return True
    return (
        outputs.get("start_date") is None
        and outputs.get("end_date") is None
        and outputs.get("target_date") is None
    )


def no_consumed_at_on_query(outputs: dict, reference_outputs: dict) -> bool:
    """When parser predicts QUERY_DAILY_STATS, consumed_at must be null.

    Mirror of `no_query_dates_on_log_food` — guards against the reverse leak
    where a query-range field (consumed_at is for writes) gets populated.
    """
    if outputs.get("action") != "QUERY_DAILY_STATS":
        return True
    return outputs.get("consumed_at") is None


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

    expected_target = _resolve_date_sentinel(reference_outputs.get("target_date"))
    actual_target = outputs.get("target_date")
    if not _dates_equivalent(expected_target, actual_target):
        return False

    return True


class NameGrade(TypedDict):
    """Grade for food name normalization quality."""

    reasoning: Annotated[str, ..., "Step-by-step reasoning for the grade."]
    is_acceptable: Annotated[
        bool, ..., "True if the name is a reasonable search-friendly normalization."
    ]


JUDGE_INSTRUCTIONS = """You are evaluating whether a food name has been properly normalized for database search.

The system performs **bilingual** catalog lookup (Hebrew + English), so the extracted food name is acceptable in **either language**.

Rules:
- Accept the name in Hebrew OR English — both are valid. The parser is instructed to keep the user's language, but cross-language output is not a failure here.
- The name should be generic and search-friendly (e.g., "Apple" / "תפוח" — not "Small sour green apple").
- Minor variations are acceptable ("Chicken" vs "Chicken Breast"; "עוף" vs "חזה עוף" — both valid).
- The name must still refer to the same food as the original user text.
- Compound dishes should be decomposed ("pasta with cheese" / "פסטה עם גבינה" → "Pasta"/"פסטה" and "Cheese"/"גבינה" separately).
- Individual ingredients from decomposed dishes are valid on their own.
- Common food product names are acceptable even if multi-word ("Protein Shake" / "שייק חלבון", "Peanut Butter" / "חמאת בוטנים").
- Do NOT penalize names that are already standard food category names.

Grade as acceptable if a bilingual nutrition catalog search for this name would reasonably find the correct food."""

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
    """LLM-as-judge: fraction of extracted food names graded acceptable.

    Accepts either Hebrew or English names — the catalog is bilingual.
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
        msg = (
            f'Original user input (Hebrew): "{inputs["question"]}"\n'
            f'Extracted food name: "{act.get("food_name", "")}"\n'
            f"\nIs this a reasonable, search-friendly canonical name (Hebrew or English) for the input?"
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
    """Upsert EXAMPLES to LangSmith: add missing, update when outputs differ.

    The code is the source of truth. To retire an example, remove it from
    EXAMPLES AND from the LangSmith UI (this sync never deletes).
    """
    existing = list(client.list_examples(dataset_id=DATASET_ID))
    existing_by_q = {ex.inputs.get("question"): ex for ex in existing}

    def _canonical(v):
        # Normalise for comparison: tuples → lists, set-iteration → sorted.
        if isinstance(v, dict):
            return {k: _canonical(v[k]) for k in sorted(v)}
        if isinstance(v, (list, tuple)):
            return [_canonical(x) for x in v]
        return v

    to_create = []
    updated = 0
    unchanged = 0

    for ex in EXAMPLES:
        q = ex["question"]
        outputs = {k: v for k, v in ex.items() if k != "question"}

        if q in existing_by_q:
            current_out = dict(existing_by_q[q].outputs or {})
            if _canonical(current_out) != _canonical(outputs):
                client.update_example(
                    example_id=existing_by_q[q].id,
                    outputs=outputs,
                )
                updated += 1
            else:
                unchanged += 1
        else:
            to_create.append(ex)

    if to_create:
        client.create_examples(
            inputs=[{"question": e["question"]} for e in to_create],
            outputs=[{k: v for k, v in e.items() if k != "question"} for e in to_create],
            dataset_id=DATASET_ID,
        )

    print(
        f"Dataset '{DATASET_NAME}': "
        f"{len(to_create)} added, {updated} updated, {unchanged} unchanged "
        f"(total {len(existing) + len(to_create)})"
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
            correct_serving,
            correct_dates,
            no_query_dates_on_log_food,
            no_consumed_at_on_query,
            food_name_quality,
        ],
        experiment_prefix=prefix,
        max_concurrency=4,
    )
    print(experiment_results.to_pandas())


if __name__ == "__main__":
    asyncio.run(main())
