# Eval Setup Skill + Evaluator Fixes

## Changes

### New
- `.claude/skills/eval-setup/SKILL.md` — Skill for creating single-step eval notebooks
  - Guides: dataset creation (UI), example design, evaluator selection, notebook generation
  - Includes node-to-prompt mapping, evaluator type guide, sentinel pattern docs
  - Experiment prefix convention: describes what's tested (model/prompt), not which node

### Fixed
- `notebooks/evals/eval_input_parser.ipynb`:
  - Judge prompt: added rules for decomposed ingredients, multi-word food names, standard categories
  - Judge model: upgraded from gpt-4o-mini to gpt-4o
  - Date evaluator: null and today treated as equivalent for start_date/end_date

### Changed
- `src/config.py` — default model changed to gpt-4.1-nano

## Next Steps
- Test eval-setup skill by creating an eval for another node (e.g., selection_node)
- Run input parser eval with gpt-4.1-nano and compare to gpt-4o baseline
- Consider eval-setup for full end-to-end (multi-turn HITL) evals in the future
