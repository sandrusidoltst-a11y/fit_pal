# Eval Debugger Skill

## Changes Implemented

### New Files
- `.claude/skills/eval-debugger/SKILL.md` — Skill definition with debug mode and clean mode
- `.claude/skills/eval-debugger/scripts/fetch_eval_failures.py` — Fetches failing runs from LangSmith, generates markdown report
- `.claude/skills/eval-debugger/scripts/clean_reports.py` — Deletes all report files

### Modified Files
- `.gitignore` — Added `notebooks/evals/reports/`

## How It Works
1. User says "debug eval <experiment-name>"
2. Script queries LangSmith for all runs with score < 1.0
3. Report generated with per-evaluator stats + failing run details (input, expected, actual, feedback)
4. Agent reads report + relevant prompt + model config → classifies each failure as PROMPT_GAP, MODEL_ISSUE, JUDGE_TOO_STRICT, or DATASET_EXPECTATION
5. Agent summarizes with actionable suggestions

## Next Steps
- Fix food_name_quality judge prompt (too strict on "Cheese", "Protein Shake")
- Update dataset: "What did I eat today?" should allow today's date as a range
- Create eval-setup skill for guiding new eval creation
- Plan next eval: selection node or full end-to-end flow
