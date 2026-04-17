# feat: Hebrew quantifier eval + input_parser prompt fix

**Date**: 2026-04-17
**Branch** (fit_pal): `refine_prompts_and_evals`
**Commits**:
- `a56f23d` — `feat: fix Hebrew quantifier parsing in input_parser; convert eval to script` (fit_pal)
- `a70c5d0` — `planning: add food-db coach-plan sync umbrella note; link from plan_category task` (brain)

**Audit**: `brain/planning/bot-ux-audit-2026-04-17.md` — Workstream 3, Fix #7

## Context

Session goal: address audit Fix #7 (Hebrew quantifier eval) and diagnose whether `input_parser_node`'s failures are model-capability or prompt-driven. Before touching the model, we wanted an eval yardstick to measure against — and we wanted the existing Hebrew eval notebook in a shape the user actually uses (script, not notebook).

## Changes

### Eval script conversion (fit_pal)
- **New**: `notebooks/evals/eval_input_parser_hebrew.py` — 1:1 port of the notebook plus:
  - Idempotent `sync_dataset` — only uploads EXAMPLES missing from LangSmith (append-only, never mutates)
  - `experiment_prefix()` reads effective model from `NODE_CONFIGS["input_node"]` / `GLOBAL_MODEL` so prefix auto-labels experiments when the model changes (`.env` swap → new prefix, clean A/B)
  - Lazy `_get_judge_llm()` — deferring the `with_structured_output(NameGrade, method="json_schema")` call past module import avoids a pydantic-v1 TypedDict schema crash that only manifests in script mode (notebook hid it via on-demand cell execution)
- **Deleted**: `notebooks/evals/eval_input_parser_hebrew.ipynb` (user does not run the notebook)

### New dataset examples (fit_pal)
11 new examples appended to the `Input Parser Hebrew` LangSmith dataset (17 → 28):

- **A: Direct audit reproductions** — `שתי פיתות`, `חמש פריכיות אורז`, `שתי פרוסות גבינה`, `מעדן חלבון`
- **B: Hebrew quantifier stress** — `שלוש ביצים`, `ארבע פרוסות לחם`, `חצי בננה`, `חצי כוס אורז`
- **C: Multi-item with word quantifiers** — `שתי פיתות ושלוש ביצים`, `שתי פרוסות גבינה עם מעדן חלבון`
- **D: Control** — `כמה חלבון יש בשלוש ביצים?` (quantifier inside a QUERY; must NOT route to LOG_FOOD — guards against overfitting the fix)

### Prompt fix (fit_pal)
Three additions to `prompts/input_parser.md` under `IF action is LOG_FOOD`:
- **Hebrew word-form quantifier table**: שתי/שתיים/שניים=2, שלוש/שלושה=3, ארבע/ארבעה=4, חמש/חמישה=5, שש/שישה=6, שבע/שבעה=7, חצי=0.5, רבע=0.25, with worked examples ("שלוש ביצים, ~50g each → 150g", "חמש פריכיות אורז, ~8g each → 40g — NOT 5g")
- **Default-serving rule**: explicit per-category defaults (beverages 240g, protein 100g, whole fruit 120g), with an explicit "never return 0g or 1g" floor
- **Multi-item quantity scoping**: forbids borrowing a quantity from a neighboring item; defaults to the rule above if an item has no quantity

User explicitly scoped out the "packaged items" default — will be picked up when the DB sync work lands real serving weights.

### Brain note (brain repo)
- **New**: `brain/planning/food-db-coach-plan-sync.md` — umbrella note for the four interlocking DB-foundation items: bilingual food names (for HITL render), `coach_category` column, estimation-path rethink (coach plan before LLM estimation), and an open question on HITL-time classification
- **Edit**: last task in Important section of `brain/TASKS.md` now links to the new umbrella note

## Eval results

Pre-fix baseline on `gpt-4.1-nano`: `amount_accuracy` **61%** (17/28 full pass).

Post-fix on the same model, same dataset: `amount_accuracy` **79%** (22/28 full pass). Other metrics unchanged (action/count/dates at 100%, food_name_quality 89% → 93%).

Individual wins (0.0 → 1.0 on amount_accuracy):
- `שתי פיתות` → 240g (exact F3 T6 audit bug fixed)
- `שלוש ביצים` → 150g
- `חמש פריכיות אורז` → 40g (was 5g)
- `חצי כוס אורז` → 79g
- `קפה` → 240g (default-serving rule working)
- `שתי פיתות ושלוש ביצים` multi-item → both correct

Remaining failures (accepted as DB-sync work):
- `ארבע פרוסות לחם` → 60g — existing `"2 slices bread → 60g"` rule-2 example anchors the model
- `שתי פרוסות גבינה` → 30g — same anchoring pattern on cheese slices
- `מעדן חלבון` → 100g — hit the "protein foods" default, landed 4g outside the tolerance band
- `חצי בננה` → 120g — regression from 60g; the "whole fruit 120g" default overrides `חצי` here. Open question for later.

## Design decisions

- **Notebook → script**: user runs evals as scripts and researches results in LangSmith UI, so the notebook was dead weight. English `eval_input_parser.ipynb` left alone — separate conversion later.
- **Script location**: kept in `notebooks/evals/` alongside the English notebook for now; a later sync-context pass can decide whether to move both to `src/scripts/`.
- **Prompt-first over model swap**: the eval failures were surgical (structure perfect, routing perfect, only `amount` wrong on a specific quantifier class). That pattern points at a missing prompt rule, not a capability ceiling. Validated by the +18pp lift from prompt alone.
- **Stopped after one round**: residual failures all point to the DB-sync work — per-food serving weights, `coach_category`, bilingual names. Iterating on the prompt further would be polishing a workaround.

## Validation

- `uv run ruff check notebooks/evals/eval_input_parser_hebrew.py` — **passed**
- Module import + dataset sync + full eval run via `uv run python notebooks/evals/eval_input_parser_hebrew.py` — **passed**, 28 examples, clean A/B vs. prior experiment

## Next steps

1. **DB-to-coach-plan sync** — follow `brain/planning/food-db-coach-plan-sync.md`. Schema migration (add `name_he` + `coach_category` columns), ingest coach's plan foods, update `food_service` for bilingual matching, then rethink the estimation path. Closes the POC blocker on `Ingest coach's plan foods` and the Important-tier `Add plan_category column` task together.
2. **After DB sync**: rerun this eval — residual failures should collapse because per-food weights will come from DB instead of prompt guesses.
3. **Not doing yet**: `gpt-4.1-mini` model swap comparison. Worth a free "ceiling check" run after the DB work, but not urgent. Experiment prefix already auto-labels, so it's a one-line `.env` change when the time comes.

## Out of scope / follow-ups

- `input_parser_node` doesn't currently accept `Runtime[ContextSchema]`, so it can't see `user_profile.nutrition_plan` even though the bot injects it. Adding this (same pattern as response_node) is a future improvement — logical companion to the DB sync work.
- `input_parser_node` uses naive `datetime.now()` (line 34) — same UTC bug that response_node had before 2026-04-14. Fix when next touching the file.
- English eval notebook (`eval_input_parser.ipynb`) not converted — separate task.
