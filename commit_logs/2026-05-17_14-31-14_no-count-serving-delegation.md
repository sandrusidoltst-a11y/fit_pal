# refactor(parser): no-count inputs delegate to catalog via `unit='serving'`

## Why

The default-serving rule in `prompts/input_parser.md` Step 2.4 hard-coded
per-category gram defaults inside the prompt (beverages 240g, protein
100g, fruit 120g, anything else "reasonable per-serving weight"). Three
problems with this design, all surfaced during the input-parser eval
investigation today:

1. **Eval/prompt mismatch on `מעדן חלבון`** — eval expected 130g (real
   container weight); the prompt rule yielded 100g (generic protein
   default). A deterministic miss, not LLM noise.
2. **Multi-item instability** — inside multi-item parses the model
   sometimes dropped the rule entirely and emitted `{count: 1, unit:
   "g"}` for the second item (would log `1g` of food). Observed ~20%
   in dogfooding.
3. **Catalog ownership inversion** — per-food default serving weight
   belongs in the catalog (`food_items.unit_weights`) where the coach
   can curate it per food, not in a prompt that has no per-food
   context.

The fix: stop guessing default grams in the prompt. For no-quantity
inputs the parser always emits `count=1, unit='serving',
amount_g=<estimate>`. The resolver chain (`resolve_amount_g`) checks
`unit_weights["serving"]` for catalog truth; if not registered, falls
back to the parser's `amount_g`. Coach curates serving weights in the
catalog as needed — loose mode, no migration, incremental.

Same shape of "stale assumption from before PR #30" as the prior commit
on this branch (`fc666f6` keep-natural-units). The whole point of the
`amount_g` safety net introduced by PR #30 was to let the parser
preserve the user's unit and let the resolver figure out grams. The
default-serving rule was a parallel hardcoded gram path that
duplicated the safety net's job for the no-count case while creating
the three problems above.

## What changed

### `prompts/input_parser.md` (Step 2.2 + 2.4 + 2.5)

- **Step 2.4 rewritten**: single rule, one shape. No-count → `{count: 1,
  unit: "serving", amount_g: <estimate>}`. The 4 hardcoded category
  bullets, the "Why grams as default" rationale, and the "Never return
  `count=1` with `unit='g'`" guard are all gone. 5 worked examples
  refreshed.
- **Step 2.2 — canonical unit vocabulary anchor**: positive directive
  listing the catalog's canonical unit keys (`g, piece, slice, cup,
  tbsp, tsp, bowl, scoop, container, bottle, can, serving`). Steers the
  model toward words the catalog actually recognizes while keeping the
  free-form fallback for unusual cases.
- **Step 2.2 — `amount_g` elevated to `**REQUIRED**`**: same rule as
  before, but promoted from a sub-bullet to its own callout line.
  Justification: with `unit='serving'` now the common no-count case,
  `amount_g` is load-bearing for the estimation path (foods not in
  catalog have only `amount_g` as the source of truth).
- **Step 2.5 (Multi-Item Quantity Scoping) example refreshed** to match
  the new shape: banana default → `{count: 1, unit: "serving", amount_g:
  120}` instead of `{count: 120, unit: "g"}`.

### `notebooks/evals/eval_input_parser_hebrew.py`

- **9 no-count expectations flipped** from `{count: <grams>, unit: "g"}`
  to `{count: 1, unit: "serving"}`. The affected examples are:
  `"קפה"`, `"מעדן חלבון"`, `"פסטה עם גבינה לצהריים"` (both items),
  `"שתיתי שייק חלבון אחרי אימון"`, `"אכלתי בננה אתמול"`, `"כמה חלבון יש
  בביצה?"`, `"כמה קלוריות יש בבננה?"`, `"שתי פרוסות גבינה עם מעדן
  חלבון"` (only the מעדן חלבון item; cheese stays `{2, slice}`),
  `"תרשום בננה ו-100 גרם אורז"` (only the banana item; rice stays `{100,
  g}`).
- **New evaluator `amount_g_present_when_non_gram`**: per-item check
  that fails if any item with `unit != "g"` is missing a numeric
  `amount_g`. Registered in the evaluators list. This is the explicit
  guard for the load-bearing rule above — drift on the parser dropping
  `amount_g` (especially on the no-count path) would silently degrade
  estimation-path gram math, and previously had no eval coverage.
- **New estimation-path example** `"שתיתי קולה דיאט"` — food that's
  unlikely to be in the catalog. Documents the intended shape under the
  new design; the eval only checks parser output, so catalog membership
  doesn't affect the assertion.

### `notebooks/evals/eval_subset.py`

- Wired `amount_g_present_when_non_gram` into `SYNC_EVALUATORS` for
  parity with the full eval. The subset script otherwise unchanged.

### `tests/unit/test_food_service_helpers.py`

- **3 new tests** in `TestResolveAmountG` exercising the three resolver
  branches for `unit='serving'`:
  - `serving` registered in `unit_weights` → catalog wins, ignoring
    `amount_g` even when present.
  - `serving` not registered, `amount_g` present → falls back to
    `amount_g`.
  - Neither catalog nor `amount_g` → last-resort fallback (returns
    `count`, logs warning).
- Mirrors existing tests (`test_unit_weights_direct_hit`,
  `test_falls_back_to_llm_estimate`,
  `test_last_resort_returns_count_when_no_estimate`) using the same
  `_food()` MagicMock helper. Sub-second, no DB, no LLM.

### `docs/plans/no-count-serving-delegation.md` (new)

- Full implementation plan from the conversation that drove this work.
  Covers design decisions (Option A loose mode, no auto-registration on
  commit, base-catalog-only resolver, canonical vocab hardcoded for
  v1), the four-phase task breakdown, and the validation chain.

### `docs/plans/no-count-serving-delegation-review-guide.md` (new)

- PR reading-order guide for the reviewer.

## Validation

| Level | Command | Result |
|---|---|---|
| Lint | `uv run ruff check .` | ✅ All checks passed |
| Unit | `uv run pytest tests/unit/ -q` | ✅ 196 passed (3 new in `TestResolveAmountG`) |
| Integration | `uv run pytest tests/integration/ -q` | ✅ 56 passed |
| Subset eval | `uv run python notebooks/evals/eval_subset.py "מעדן חלבון" "קפה" "פסטה עם גבינה" "שייק חלבון" "קולה דיאט" "אכלתי בננה אתמול" "כמה קלוריות יש בבננה"` | ✅ 8/8 examples × 7 dimensions |
| Full eval | `uv run python notebooks/evals/eval_input_parser_hebrew.py` | ✅ 36/36 on every dimension |

### Eval comparison

| Dimension | Before (start of session) | After (this branch) |
|---|---|---|
| correct_action | 100% | 100% |
| correct_item_count | 100% | 100% |
| food_name_quality | 100% | 100% |
| no_consumed_at_on_query | 100% | 100% |
| no_query_dates_on_log_food | 100% | 100% |
| correct_dates | 91% | **100%** (+9 pts, dates fix `545d456`) |
| correct_serving | 90% | **100%** (+10 pts, units fix `fc666f6` + this commit) |
| amount_g_present_when_non_gram | — | **100%** (new guard) |

LangSmith experiment: `input-parser-hebrew-gpt-5.4-mini-4cf59d7c`
(session `a129d020-56d6-4ef4-b95b-677d8681e1c2`).

## What's next

- **Estimated-food rows still don't auto-register `serving`.** Per the
  plan's Option A decision, the cost is that subsequent logs of the
  same estimated food re-estimate `amount_g` via LLM each time —
  variance until coach curates. Acceptable now because no production
  users are affected. Worth revisiting once the coach dashboard exists
  (Option C from the plan: register + flag for review).
- **Canonical unit vocabulary is hardcoded in the prompt.** Future
  enhancement: regenerate from `SELECT DISTINCT jsonb_object_keys(unit_weights) FROM food_items`
  at server startup, inject into the prompt.
- **`correct_serving` evaluator only checks `count` + `unit`,** not the
  resolved gram value. Resolver correctness is unit-tested directly,
  so this is a clean separation. If we ever want an end-to-end
  parser→resolver assertion in the eval, the architecture supports it
  but it would couple eval to catalog state (eval flakes on catalog
  change). Currently considered out of scope.
- **`coach_food_mappings.serving_amount_g` not touched.** Per the plan,
  coach overrides live on a different table and feed
  plan-compliance math (`compute_servings`), not the resolver. If we
  ever want coach-level overrides at the resolver too, that's a
  separate ADR.

## References

- Plan: `docs/plans/no-count-serving-delegation.md`
- Reading guide: `docs/plans/no-count-serving-delegation-review-guide.md`
- Prior commits on parent branch (`fix/last-N-days-rolling-exclusive`):
  - `545d456` fix(parser): "last N days" / "אחרון" range queries exclude today
  - `fc666f6` fix(parser): keep natural units, stop converting cups/halves to grams
- Resolver chain introduced: PR #30 (multi-unit weights + synonyms)
