# fix(parser): keep natural units, stop converting cups/halves to grams

## Why

Two serving failures on the Hebrew input-parser eval traced to the same
root cause:

- `חצי בננה` → parser emitted `60g` instead of `0.5 piece` (lost the
  piece unit on a fractional-quantifier piece-bucket food).
- `אכלתי כוס אורז` → parser emitted `1 cup, amount_g=158`; eval expected
  `158g` and marked it as a failure.

Investigation surfaced **two contradicting rules** in `input_parser.md`:

- **Step 2.2** (the safety-net design): "when `unit != 'g'`, you MUST
  also emit `amount_g`" — and the worked example
  `"1 cup of rice" → {count: 1, unit: "cup", amount_g: 158}` keeps the
  cup.
- **Step 2.3** (Hebrew quantifiers, stale): worked example
  `"חצי כוס אורז" → {count: 79, unit: "g"}` converts cup to grams
  because "rice is gram-native."

Same food, same unit, two different output shapes. The convert-in-parser
behavior predated the `unit_weights JSONB` work in PR #30, which moved
weight resolution into a resolver chain (`unit_weights` → `unit_synonyms`
→ parser's `amount_g` safety net). After that PR, converting natural
units to grams in the parser throws away information the resolver was
designed to consume — and degrades the HITL preview ("you logged 1 cup
of rice (158g)" reads better than "158g of rice").

Product call on the eval expectation: the parser was right on
`אכלתי כוס אורז`. Eval expectation was the stale one.

## What changed

### `prompts/input_parser.md`

Step 2.2 rewritten so there is exactly one rule: explicit grams →
`unit="g"`, anything else → keep that unit + emit `amount_g`. The
"gram-native exception" is gone — it now applies only to the
default-serving fallback in Step 2.4 (no quantity given at all).

Step 2.3 gains a fractional-quantifier clarification ("Half a banana is
`count=0.5, unit='piece'`, NOT `count=60, unit='g'`") and the stale
`חצי כוס אורז` worked example was replaced with one that keeps the cup
unit. A new `חצי בננה` worked example was added to make the
piece-bucket fractional case explicit.

### `notebooks/evals/eval_input_parser_hebrew.py`

Two expectations flipped:

- `אכלתי כוס אורז` → `{count: 1, unit: "cup"}` (was `158g`).
- `חצי כוס אורז` → `{count: 0.5, unit: "cup"}` (was `79g`).

`amount_g` not asserted by `correct_serving` — would require an
evaluator change. Logged as follow-up below.

### `notebooks/evals/eval_subset.py` (new)

Subset runner that takes question substrings (CLI args or hardcoded
defaults) and runs only those through `input_parser_node`. Reuses the
canonical `EXAMPLES` and evaluator functions from
`eval_input_parser_hebrew.py` — single source of truth. Skips LangSmith
entirely, scores locally, prints per-row + aggregate. Built for tight
iteration loops on specific failures without paying for a 35-row run or
polluting LangSmith with duplicate experiments.

## Validation

Bucket-A targets, run through `eval_subset.py`:

| Query | Before | After |
|---|---|---|
| `חצי בננה` | `60g` ❌ | `0.5 piece, amount_g=60` ✅ |
| `אכלתי כוס אורז` | `1 cup, amount_g=158` (eval-wrong) ❌ | `1 cup, amount_g=158` ✅ |
| `חצי כוס אורז` | `79g` ❌ | `0.5 cup, amount_g=79` ✅ |

Three remaining serving failures are unrelated to Bucket A and tracked
in the follow-ups below.

## What's next

- **Bucket B (default-serving precision)** — `מעדן חלבון` on its own
  returns `100g` (generic protein default) but the eval expects `130g`
  (one actual container). Inside a multi-item input the model is
  jittery: same prompt path produced `1g`, `100g`, and `1 piece,
  amount_g=150` across runs. Real root cause is the vagueness of
  "anything else: a reasonable per-serving weight in grams" — the
  default-serving rule needs either tighter prompt guidance or a
  catalog/resolver-side default-unit-weight lookup.
- **Bucket C (aspirational eval expectations)** —
  `פסטה עם גבינה לצהריים` expects `200g pasta + 30g cheese`
  (meal-context defaults: pasta-as-meal vs. cheese-as-topping). No
  parser-side rule supports this; arguably none should. Relax the eval
  expectation to accept generic defaults.
- **`correct_serving` evaluator gap** — currently only checks `count` +
  `unit`. With the safety-net design now load-bearing, `amount_g`
  accuracy on natural-unit emissions is silently untested. Worth
  adding once Bucket B/C are resolved so we have a clean baseline.

## References

- Prior commit on branch: `545d456 fix(parser): "last N days" / "אחרון" range queries exclude today`
- PR #30 (multi-unit weights + synonyms — the resolver chain this fix depends on)
- Companion eval log: `commit_logs/2026-05-16_14-31-43_last-N-days-rolling-exclusive.md`
