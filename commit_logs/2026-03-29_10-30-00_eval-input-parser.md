# Input Parser Single-Step Evaluation

## Changes Implemented

### New Files
- `notebooks/evals/eval_input_parser.ipynb` — LangSmith evaluation notebook for `input_parser_node`
  - 15 examples covering LOG_FOOD, QUERY_FOOD_INFO, QUERY_DAILY_STATS, CHITCHAT
  - 5 evaluators: action classification, item count, amount accuracy (±20%), date parsing, food name quality (LLM-as-judge)
  - Uses dataset created in LangSmith UI under fit-pal-agent project (dataset ID hardcoded)
  - Results tracked via `client.aevaluate()` and displayed as pandas DataFrame

- `.agent/plans/eval-input-parser-single-step.md` — Implementation plan

### Modified Files
- `prompts/input_parser.md` — Clarified date range semantics: "last 3 days" is inclusive of today
- `PRD.md` — Added Phase 4 task: display queried date ranges to user in response
- `pyproject.toml` / `uv.lock` — Added `ipykernel` dev dependency for notebook kernel

## Key Decisions
- Eval notebook calls node directly (no server needed), not raw LLM
- Dataset created in LangSmith UI inside project (SDK doesn't support project-scoped dataset creation)
- Date sentinels (RELATIVE, YESTERDAY_NOON, TODAY) resolve at eval time to avoid stale examples
- Only food_name_quality uses LLM-as-judge; other 4 evaluators are deterministic

## Next Steps
- Fix food_name_quality judge prompt (too strict — rejected "Protein Shake")
- Add more edge case examples to dataset
- Plan next eval: selection node or full end-to-end flow
- Implement PRD task: display actual date ranges in response node
