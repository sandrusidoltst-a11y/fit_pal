# PR Reading Guide — no-count → `unit='serving'` delegation

## Why this PR exists

Read first to start with intent, not code:

1. **`docs/plans/no-count-serving-delegation.md`** — the plan with full
   design rationale. The "Notes" section at the bottom is where most
   tradeoffs are spelled out.
2. **`commit_logs/2026-05-17_14-31-14_no-count-serving-delegation.md`** — the
   commit log. The "Why" and "Eval comparison" sections summarize what
   moves and by how much.

If you only read one thing before the diff, read the commit log's "Why"
section.

## The keystone change

The whole PR hinges on one rule swap in one file:

3. **`prompts/input_parser.md`** — Step 2.4 (default-serving rule)
   is rewritten from a 4-bucket per-category gram table to a single
   universal rule: `count=1, unit='serving', amount_g=<estimate>`.
   Once you understand this, every other diff is a consequence:
   the eval flips because the expected output shape changed; the
   unit tests cover the resolver branch this new shape exercises;
   the canonical vocab anchor in Step 2.2 and the `amount_g`
   REQUIRED elevation exist to make the new rule load-bearing.

## The writer

The parser is the writer here. It hasn't changed — only its prompt
has. So there's no `src/` diff to read for "construction of the new
shape." The prompt rewrite IS the writer change.

Worth confirming while reading the prompt:
- Step 2.4 reads as one rule, not categories.
- Step 2.2's canonical vocabulary anchor is positively framed (no
  "never use X" — those backfire on LLMs).
- Step 2.2's `amount_g` REQUIRED callout explicitly mentions
  `unit='serving'` as a triggering case.

## The readers

The resolver chain (`src/services/food_service.py::resolve_amount_g`)
is the primary reader, but **it's unchanged** — this is the whole
point of the design. The existing chain already handles
`unit='serving'` correctly: rule 2 if registered in `unit_weights`,
rule 4 fallback to `amount_g`, rule 5 last-resort if neither.

4. **`tests/unit/test_food_service_helpers.py`** — three new tests
   that exercise the three resolver branches for `unit='serving'`. The
   tests document the contract the resolver provides; the production
   code itself didn't need any change.

## Adjacent updates

5. **`notebooks/evals/eval_input_parser_hebrew.py`** — the eval is
   updated in three places:
   - **9 expectation flips** (search the diff for
     `"count": 1, "unit": "serving"` to see them all). Each flip
     corresponds to one example where the user gave no count and the
     parser used to emit a gram default. The flip is purely
     mechanical — same example, different expected shape.
   - **New evaluator** `amount_g_present_when_non_gram` — the guard
     for the load-bearing rule. Fails if any item with `unit != 'g'`
     is missing a numeric `amount_g`. Per-item granularity. Registered
     in the evaluators list at the bottom of the file.
   - **New estimation-path example** `"שתיתי קולה דיאט"` — a food
     unlikely to be in the catalog. Documents the intended parser
     shape under the new design.

6. **`notebooks/evals/eval_subset.py`** — two-line change to wire
   the new evaluator into `SYNC_EVALUATORS` for parity with the full
   eval. Subset script is otherwise unchanged.

## Things worth flagging while reviewing

- **Loose mode (Option A): `serving` is OPTIONAL in `unit_weights`,
  not enforced.** Foods that haven't been curated with a `serving`
  key will fall through to the parser's `amount_g` estimate on
  no-count inputs — meaning run-to-run LLM variance for that food
  until a coach registers a value. The plan calls this out
  explicitly; we chose it over auto-registration because no
  production users are affected yet and "lock in the first LLM
  guess" is a worse failure mode for a curated catalog.
- **Estimated-food rows still won't get `serving` auto-registered
  on commit.** Consequence: the same estimated food re-logged in
  separate sessions will have different gram values each time
  (LLM-estimated `amount_g`). Same design call as above; will
  revisit once the coach dashboard exists for review workflows.
- **Canonical unit vocabulary is HARDCODED in the prompt.** It's
  not dynamically generated from `SELECT DISTINCT
  jsonb_object_keys(unit_weights)`. That's intentional v1 simplicity;
  future task could swap to runtime generation as the catalog grows.
- **`correct_serving` evaluator was NOT extended to assert
  `amount_g` values** — only the new `amount_g_present_when_non_gram`
  guards presence. Reason: `amount_g` is an LLM estimate with
  inherent variance; asserting exact values would re-introduce the
  same kind of eval flake we just eliminated by deleting the
  hardcoded gram defaults. Resolver correctness (which uses
  `amount_g`) is unit-tested directly.
- **`coach_food_mappings.serving_amount_g` is NOT touched.** Per-coach
  serving weights live on a different table and feed the
  plan-compliance math (`compute_servings`), not the resolver. If
  this PR's design felt like it implied coach-level resolver
  overrides, it doesn't — separate concern, separate ADR if we
  ever want it.
- **Multi-item example in Step 2.5 of the prompt was updated** to
  match the new shape (banana: `{count: 1, unit: "serving",
  amount_g: 120}` instead of `{count: 120, unit: "g"}`). A free
  piggyback on the main rewrite — stale example would've contradicted
  the new Step 2.4 rule.

## Skip-able

- `docs/plans/no-count-serving-delegation.md` is the full plan and
  is long. The commit log is a tighter summary; read it first and
  only dive into the plan for the design-tradeoff rationale.
- The eval flips in `eval_input_parser_hebrew.py` are mechanical and
  all the same shape — once you've seen one or two, the rest are
  predictable. Don't read all 9 individually.
