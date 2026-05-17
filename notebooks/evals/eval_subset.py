"""Run a SUBSET of the Hebrew input-parser eval — by question substring match.

Skips LangSmith entirely: runs the parser locally and scores against the
expectations in ``eval_input_parser_hebrew.EXAMPLES``. Useful for tight
iteration loops on specific failures without paying for a full 35-row run
or polluting LangSmith with duplicate experiments.

Usage:
    # default — runs the current "failing" set hardcoded below
    uv run python notebooks/evals/eval_subset.py

    # match by question substring (any one is enough; case-sensitive)
    uv run python notebooks/evals/eval_subset.py "כוס אורז" "חצי בננה"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

# Reuse the canonical examples + evaluator functions from the main eval file
from notebooks.evals.eval_input_parser_hebrew import (  # noqa: E402
    EXAMPLES,
    amount_g_present_when_non_gram,
    correct_action,
    correct_dates,
    correct_item_count,
    correct_serving,
    food_name_quality,
    no_consumed_at_on_query,
    no_query_dates_on_log_food,
    run_input_parser,
)

DEFAULT_QUERIES = [
    "פסטה עם גבינה לצהריים",
    "אכלתי כוס אורז",
    "מעדן חלבון",
    "חצי בננה",
    "שתי פרוסות גבינה עם מעדן חלבון",
    "חצי כוס אורז",
]

SYNC_EVALUATORS = [
    correct_action,
    correct_item_count,
    correct_serving,
    amount_g_present_when_non_gram,
    correct_dates,
    no_consumed_at_on_query,
    no_query_dates_on_log_food,
]
ASYNC_EVALUATORS = [food_name_quality]  # take (inputs, outputs, ref)


def _score_value(result) -> float:
    """Normalize evaluator output (bool or dict-with-score) to a 0.0–1.0 float."""
    if isinstance(result, dict):
        return float(result.get("score", 0.0))
    return 1.0 if bool(result) else 0.0


def _score_comment(result) -> str:
    """Extract human-readable comment from a dict evaluator; empty for bools."""
    if isinstance(result, dict):
        return result.get("comment", "") or ""
    return ""


async def run_subset(queries: list[str]) -> None:
    matches: list[dict] = []
    seen_questions: set[str] = set()
    unmatched: list[str] = []
    for q in queries:
        found = [ex for ex in EXAMPLES if q in ex["question"]]
        if not found:
            unmatched.append(q)
            continue
        for ex in found:
            if ex["question"] not in seen_questions:
                matches.append(ex)
                seen_questions.add(ex["question"])

    if unmatched:
        print(f"⚠️  No example matched: {unmatched}\n")
    if not matches:
        print("Nothing to run.")
        return

    print(f"Running {len(matches)} example(s)\n")

    summary: dict[str, list[float]] = {
        fn.__name__: [] for fn in (*SYNC_EVALUATORS, *ASYNC_EVALUATORS)
    }

    for ex in matches:
        inputs = {"question": ex["question"]}
        outputs = await run_input_parser(inputs)
        ref = ex  # ref shape mirrors EXAMPLES dict — evaluators read .get(...) on it
        print(f"Q: {ex['question']}")
        print(f"  parser → action={outputs['action']}  items={outputs['items']}")
        if outputs.get("target_date") or outputs.get("start_date"):
            print(
                f"           target_date={outputs.get('target_date')}  "
                f"start={outputs.get('start_date')}  end={outputs.get('end_date')}"
            )
        for evaluator in SYNC_EVALUATORS:
            result = evaluator(outputs, ref)
            score = _score_value(result)
            summary[evaluator.__name__].append(score)
            if score < 1.0:
                print(f"    ❌ {evaluator.__name__}  {_score_comment(result)}")
        for evaluator in ASYNC_EVALUATORS:
            result = await evaluator(inputs, outputs, ref)
            score = _score_value(result)
            summary[evaluator.__name__].append(score)
            if score < 1.0:
                print(f"    ❌ {evaluator.__name__}  {_score_comment(result)}")
        print()

    print("=" * 60)
    print("Aggregate (this subset):")
    for name, scores in summary.items():
        if not scores:
            continue
        avg = sum(scores) / len(scores)
        mark = "✅" if avg == 1.0 else "❌"
        passing = int(sum(scores))
        total = len(scores)
        print(f"  {mark} {name:30s}  {passing}/{total}  =  {avg * 100:.0f}%")


def main() -> None:
    queries = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_QUERIES
    asyncio.run(run_subset(queries))


if __name__ == "__main__":
    main()
