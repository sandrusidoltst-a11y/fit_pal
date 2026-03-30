"""Fetch and report on failing eval runs from a LangSmith experiment.

Usage:
    uv run .claude/skills/eval-debugger/scripts/fetch_eval_failures.py <experiment-name>
    uv run .claude/skills/eval-debugger/scripts/fetch_eval_failures.py <experiment-name> --raw

Arguments:
    experiment-name    Full experiment name from LangSmith UI (e.g., input-parser-eval-abc123)
    --raw              Print raw JSON for each failing run (instead of formatted markdown)

Output:
    Prints markdown report to stdout.
    Saves report to notebooks/evals/reports/YYYY-MM-DD_<experiment-name>.md
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime

from dotenv import load_dotenv


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def fetch_failures(client, experiment_name, *, raw=False):
    """Fetch all runs from an experiment and identify failures."""

    # Get all runs in the experiment
    runs = list(client.list_runs(project_name=experiment_name, limit=100))

    if not runs:
        print(f"No runs found for experiment '{experiment_name}'", file=sys.stderr)
        sys.exit(1)

    if len(runs) >= 100:
        print("WARNING: Hit 100 run limit. Results may be incomplete.", file=sys.stderr)

    # Collect feedback for all runs
    all_run_ids = [r.id for r in runs]
    all_feedback = list(client.list_feedback(run_ids=all_run_ids))

    # Group feedback by run_id
    feedback_by_run = defaultdict(list)
    for fb in all_feedback:
        feedback_by_run[fb.run_id].append(fb)

    # Per-evaluator stats
    evaluator_stats = defaultdict(lambda: {"pass": 0, "fail": 0})

    # Identify failing runs
    failing_runs = []
    for run in runs:
        run_feedback = feedback_by_run.get(run.id, [])
        has_failure = False

        for fb in run_feedback:
            score = fb.score
            if score is not None and score < 1.0:
                has_failure = True
                evaluator_stats[fb.key]["fail"] += 1
            elif score is not None:
                evaluator_stats[fb.key]["pass"] += 1

        if has_failure:
            # Try to get expected outputs from the dataset example
            expected = None
            if run.reference_example_id:
                try:
                    example = client.read_example(run.reference_example_id)
                    expected = example.outputs
                except Exception:
                    expected = None

            failing_runs.append({
                "run_id": str(run.id),
                "inputs": run.inputs,
                "outputs": run.outputs,
                "expected": expected,
                "error": run.error,
                "feedback": [
                    {
                        "key": fb.key,
                        "score": fb.score,
                        "comment": fb.comment,
                    }
                    for fb in run_feedback
                ],
            })

    # Sort: most failures first
    failing_runs.sort(key=lambda r: sum(1 for fb in r["feedback"] if fb["score"] is not None and fb["score"] < 1.0), reverse=True)

    total = len(runs)
    failed = len(failing_runs)
    passed = total - failed

    return {
        "experiment_name": experiment_name,
        "total": total,
        "passed": passed,
        "failed": failed,
        "evaluator_stats": dict(evaluator_stats),
        "failing_runs": failing_runs,
    }


def format_report(data):
    """Format the failure data as a markdown report."""
    lines = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines.append(f"# Eval Report: {data['experiment_name']}")
    lines.append(f"Generated: {now_str}")
    lines.append("")

    # Summary
    total = data["total"]
    passed = data["passed"]
    failed = data["failed"]
    pass_pct = (passed / total * 100) if total > 0 else 0
    fail_pct = (failed / total * 100) if total > 0 else 0

    lines.append("## Summary")
    lines.append(f"- **Total runs**: {total}")
    lines.append(f"- **Passed**: {passed} ({pass_pct:.0f}%)")
    lines.append(f"- **Failed**: {failed} ({fail_pct:.0f}%)")
    lines.append("")

    # Per-evaluator table
    if data["evaluator_stats"]:
        lines.append("### Per-Evaluator Scores")
        lines.append("| Evaluator | Pass | Fail | Pass Rate |")
        lines.append("|-----------|------|------|-----------|")
        for name, stats in sorted(data["evaluator_stats"].items()):
            p = stats["pass"]
            f = stats["fail"]
            rate = (p / (p + f) * 100) if (p + f) > 0 else 0
            lines.append(f"| {name} | {p} | {f} | {rate:.0f}% |")
        lines.append("")

    # Failing runs
    if data["failing_runs"]:
        lines.append("## Failing Runs")
        lines.append("")

        for i, run in enumerate(data["failing_runs"], 1):
            run_id_short = run["run_id"][:12]
            lines.append(f"### Run {i}: {run_id_short}")
            lines.append("")

            # Input
            question = ""
            if run["inputs"] and "question" in run["inputs"]:
                question = run["inputs"]["question"]
            elif run["inputs"]:
                question = json.dumps(run["inputs"], default=_json_default)
            lines.append(f"**Input**: \"{question}\"")
            lines.append("")

            # Expected output
            if run["expected"]:
                lines.append("**Expected**:")
                lines.append("```json")
                lines.append(json.dumps(run["expected"], indent=2, default=_json_default))
                lines.append("```")
            else:
                lines.append("**Expected**: N/A")
            lines.append("")

            # Actual output
            if run["outputs"]:
                lines.append("**Actual**:")
                lines.append("```json")
                lines.append(json.dumps(run["outputs"], indent=2, default=_json_default))
                lines.append("```")
            lines.append("")

            # Error
            if run["error"]:
                lines.append(f"**Error**: {run['error']}")
                lines.append("")

            # Failed evaluators
            failed_evals = [fb for fb in run["feedback"] if fb["score"] is not None and fb["score"] < 1.0]
            passed_evals = [fb for fb in run["feedback"] if fb["score"] is not None and fb["score"] >= 1.0]

            if failed_evals:
                lines.append("**Failed Evaluators**:")
                for fb in failed_evals:
                    comment = f", comment=\"{fb['comment']}\"" if fb["comment"] else ""
                    lines.append(f"- `{fb['key']}`: score={fb['score']}{comment}")
                lines.append("")

            if passed_evals:
                lines.append("**Passed Evaluators**:")
                for fb in passed_evals:
                    lines.append(f"- `{fb['key']}`: score={fb['score']}")
                lines.append("")

            lines.append("---")
            lines.append("")

    return "\n".join(lines)


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

    experiment_name = sys.argv[1]
    raw = "--raw" in sys.argv

    from langsmith import Client
    client = Client()

    data = fetch_failures(client, experiment_name)

    if raw:
        print(json.dumps(data, indent=2, default=_json_default))
    else:
        report = format_report(data)
        print(report)

        # Save report to file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Navigate: .claude/skills/eval-debugger/scripts/ -> project root
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))
        reports_dir = os.path.join(project_root, "notebooks", "evals", "reports")
        os.makedirs(reports_dir, exist_ok=True)

        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"{date_str}_{experiment_name}.md"
        filepath = os.path.join(reports_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)

        print(f"\nReport saved to: {filepath}", file=sys.stderr)


if __name__ == "__main__":
    main()
