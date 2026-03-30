"""Delete all eval report files from notebooks/evals/reports/.

Usage:
    uv run .claude/skills/eval-debugger/scripts/clean_reports.py
"""

import glob
import os
import sys


def main():
    # Navigate: .claude/skills/eval-debugger/scripts/ -> project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))
    reports_dir = os.path.join(project_root, "notebooks", "evals", "reports")

    if not os.path.isdir(reports_dir):
        print("No reports directory found. Nothing to clean.")
        sys.exit(0)

    files = glob.glob(os.path.join(reports_dir, "*.md"))

    if not files:
        print("No report files found. Already clean.")
        sys.exit(0)

    for f in files:
        os.remove(f)

    print(f"Deleted {len(files)} report file(s) from {reports_dir}")


if __name__ == "__main__":
    main()
