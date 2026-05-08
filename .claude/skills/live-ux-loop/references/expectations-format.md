# Expectations File Format

`expectations.md` is the single user-maintained file that declares **what** to evaluate, **how** to evaluate it, and **what to do when results fall outside acceptable ranges**. It carries three responsibilities — scoring rubric, regression thresholds, and runtime behavioral rules — because they all reference the same dimensions and need to stay in sync.

## Why this shape

- **One file, three responsibilities, one source of truth.** A behavioral rule like *"if `tone` scores low, abort the scenario"* references a dimension that has to be defined somewhere. Splitting dimensions across files invites drift between rule and rubric. Keeping them together makes the cross-reference physical: scroll up to see what a rule means.
- **User-defined evaluation methods, not a fixed schema.** Different dimensions need different judgment shapes — pass/fail for "language consistency", a 0-3 rubric for "tone", a checklist for "HITL clarity". The format defines *structure* (where dimensions, thresholds, and rules live) but doesn't dictate how any given dimension is scored.
- **Cross-referenced by name.** Dimensions are addressed by their heading text. Regression thresholds and behavioral rules use those names verbatim. Misspellings show up as findings, not silent matches.

## Top-level file structure

```markdown
# Expectations

## Dimensions
<one subsection per dimension>

## Regression thresholds
<per-metric thresholds for the Step 7 eval comparison>

## Behavioral rules
<runtime rules triggered by dimension scores or `expect:` divergences>
```

The three sections are required even if a section is empty — leaving the heading present makes the file scannable and keeps drafting consistent.

## Section 1: Dimensions

Each dimension is declared as a `### <name>` subsection under `## Dimensions`. The name is the canonical reference used everywhere else in the file *and* in `scenarios.md`'s `Dimensions:` lines.

### Required per-dimension fields

```markdown
### tone
**What:** does the bot sound like a coach inside the FitPal method, not a chatbot?
**How to evaluate:** 0-3 rubric.
- 3 = unmistakably coach voice — references the trainee's current state, gives forward-looking guidance, no filler
- 2 = coach-leaning but generic — acknowledges but doesn't condition on context
- 1 = neutral / chatbot-flat — no coach voice
- 0 = breaks the role (apologetic, robotic, contradictory)
**Output:** integer 0-3 + one-sentence justification quoting the bot reply.
```

| Field | Required | What it means |
|---|---|---|
| `### <name>` | yes | Canonical dimension name. Used by `scenarios.md` `Dimensions:` and by Behavioral rules. Keep it lowercase, hyphens for spaces, no quotes. |
| `**What:**` | yes | One-sentence description of what this dimension covers. Helps a reader (or future you) understand the purpose without reading the rubric. |
| `**How to evaluate:**` | yes | The judgment process. Free-form — pick the shape that fits the dimension. See "Evaluation method shapes" below. |
| `**Output:**` | yes | What the scorer must return per scenario for this dimension. Determines whether downstream rules can compare to a numeric threshold or just `pass`/`fail`. |

### Optional per-dimension fields

```markdown
**Examples:**
- ✅ pass: "אתה אחרי אימון? כדאי להוסיף 20–30 גרם פחמימות עכשיו" (specific, time-conditioned)
- ❌ fail: "תמשיך בכיוון הזה!" (empty motivational filler)

**Cross-reference:** see `docs/nutrition-method.md` § "Coach voice".
```

| Field | When to include |
|---|---|
| `**Examples:**` | When the rubric is subjective and a few anchors clarify intent more than prose. |
| `**Cross-reference:**` | When the source-of-truth lives elsewhere (e.g., `docs/nutrition-method.md`). The agent reads the referenced section as part of scoring. |

### Evaluation method shapes (pick what fits)

Different dimensions naturally fit different shapes. The format does not pick one — the user does, per dimension.

- **Pass/fail rule**: a single yes/no condition. Output is `pass` or `fail`.
- **N-point scoring rubric**: anchors at each level. Output is the score + reasoning. Most flexible for subjective dimensions.
- **Checklist (all-must-hold)**: a list where every item must be true to pass. Output is `pass`/`fail` plus which items failed.
- **Weighted sub-criteria**: each sub-criterion has a score and a weight; final score is the weighted sum. Output is the composite score plus per-sub-criterion breakdown.
- **Examples-based**: a list of "this passes" and "this fails" examples. The judge classifies the new reply by similarity. Output is the classification + reasoning.
- **External-reference**: *"see `docs/nutrition-method.md` section X — match its rules"*. Output shape declared explicitly.

If a dimension's `How to evaluate:` doesn't fit one of these and isn't operational enough for a judge to act on, that's a drafting bug — surface it during Mode B authoring.

## Section 2: Regression thresholds

These are the bookend thresholds used by Step 7 (post-loop regression check) — they apply to **eval metrics**, which are distinct from dimensions:
- A *dimension* is scored per-scenario by the agent reading the conversation.
- An *eval metric* is the number a LangSmith experiment outputs (e.g., `correct_dates: 0.91`).

```markdown
## Regression thresholds

- `correct_dates`: max -2pp        # tolerable LLM-judge variance
- `food_name_quality`: no drop      # any drop blocks the PR
- `correct_action`: max -1pp
```

| Format | Meaning |
|---|---|
| `<metric>: max -Npp` | Final score may drop at most N percentage points below baseline. |
| `<metric>: no drop` | Any drop blocks the PR. |
| `<metric>: max -X` | Same idea for non-percentage metrics (e.g., raw counts). |

Metrics not listed here are **not regression-checked**. If the eval reports a metric and the user hasn't declared a threshold, the agent surfaces it: *"`<metric>` is in the eval output but has no threshold — should it block on regression, or is it informational?"*

## Section 3: Behavioral rules

Behavioral rules trigger **during** or **between** scenarios based on observed outcomes — dimension scores, divergences from the scenario's `expect:`, or trace signals. They drive runtime decisions that would otherwise be hard-coded into the loop driver.

Each rule has a `when:` clause (the trigger condition) and a `do:` clause (the action). Rules are evaluated in order; the first matching rule fires.

```markdown
## Behavioral rules

- when: turn expected `interrupt` but bot returned `final`
  do: record finding (dimension: hitl-clarity, severity: high), abort scenario, continue to next

- when: turn expected `final` but bot returned `interrupt`
  do: record finding (severity: medium), send resume "cancel", continue

- when: dimension `tone` scored below 2
  do: record finding (severity: high), abort scenario

- when: any FAILED processing_result in trace
  do: record finding (dimension: pipeline, severity: high), continue

- when: bot returns no response within 60s
  do: abort scenario, record finding (severity: high, bucket: pipeline)
```

### `when:` clause — trigger types

| Trigger | Shape | Notes |
|---|---|---|
| `expect:` divergence | `turn expected <interrupt\|final> but bot returned <final\|interrupt>` | Detected by the runner after each turn. |
| Dimension threshold | `dimension <name> scored <op> <value>` where `<op>` is `below`, `above`, `equals` | Evaluated after Step 4 scoring. References a dimension defined in Section 1. |
| Trace signal | `any FAILED processing_result in trace`, `<node_name> emitted error`, etc. | Evaluated in Step 3 (trace inspection). |
| DB invariant | `daily_logs row missing for committed item` | Evaluated in Step 4 (DB verification). |
| Timeout | `bot returns no response within Ns` | Detected by the runner during transport. |

### `do:` clause — actions

| Action | Effect |
|---|---|
| `record finding(...)` | Adds a finding to the session report. Required arguments: `severity` (low/med/high). Optional: `dimension`, `bucket`, custom note. |
| `abort scenario` | Skips remaining turns of the current scenario. Loop continues to the next scenario. |
| `continue` | No-op for runtime; the rule fired but the loop proceeds normally. Used when you only want to record a finding. |
| `retry` | Re-sends the same user message once. Use sparingly — if the bot is non-deterministic enough to need retries, that's itself a finding. |
| `send resume "<text>"` | Send a custom resume reply. Useful for graceful recovery when the bot interrupted unexpectedly. |
| `abort session` | Stops the entire UX-loop session. Used for critical failures (e.g., dev server crashed). |

Multiple actions in one `do:` are separated by commas and execute in order.

### Rule ordering

Rules are tried top-to-bottom. **First match wins.** Put more specific rules above more general ones.

If no rule matches a given trigger, the default behavior is `continue` (record nothing, proceed). This is intentional — silent passes are normal; only divergences and threshold breaches need declared rules.

## Worked example — minimal `expectations.md`

```markdown
# Expectations

## Dimensions

### tone
**What:** does the bot sound like a coach inside the FitPal method?
**How to evaluate:** 0-3 rubric.
- 3 = unmistakably coach voice — references trainee state, forward-looking guidance, no filler
- 2 = coach-leaning but generic
- 1 = neutral / chatbot-flat
- 0 = breaks role
**Output:** integer 0-3 + one-sentence justification quoting the reply.

### language-consistency
**What:** the bot replies in the user's language with no mid-reply switches.
**How to evaluate:** pass/fail.
- pass: every word in the reply is in the user's language (Hebrew or English), including nutrition terms (`מנות`/`servings`, `חלבון`/`protein`).
- fail: any English word inside a Hebrew reply, or vice versa.
**Output:** `pass` or `fail` + the offending word(s) on fail.

### budget-reasoning
**What:** when asked about remaining macros, the bot computes `target − consumed` instead of restating absolutes.
**How to evaluate:** checklist (all must hold for pass).
- references the daily target for the macro asked about
- subtracts what's been consumed
- states the remainder explicitly (e.g., "you have 30g protein left")
- if relevant, conditions on time-of-day
**Output:** `pass` or `fail` + which checklist items failed.

## Regression thresholds

- `correct_dates`: max -2pp
- `correct_action`: no drop
- `food_name_quality`: max -3pp

## Behavioral rules

- when: turn expected `interrupt` but bot returned `final`
  do: record finding (dimension: hitl-clarity, severity: high), abort scenario, continue to next

- when: dimension `tone` scored below 2
  do: record finding (severity: med), continue

- when: dimension `language-consistency` scored fail
  do: record finding (severity: high), continue

- when: any FAILED processing_result in trace
  do: record finding (dimension: pipeline, severity: high), continue
```

## Common pitfalls

- **Defining a dimension without an operational `How to evaluate:`.** *"Should sound natural"* is not actionable. The judge needs a rubric, not vibes.
- **Behavioral rules referencing undeclared dimensions.** If a rule says `dimension foo scored below 2` but `foo` isn't in Section 1, the rule never fires. Surface as a drafting error.
- **Putting deterministic copy assertions in a dimension.** *"Bot must say exactly 'logged 100g chicken'"* doesn't survive contact with an LLM. Phrase as a checklist or rubric instead.
- **Mixing dimensions and metrics.** Dimensions are scored per-scenario by the agent. Metrics come from LangSmith experiments. They share the regression-threshold mechanic but are populated by different processes — don't blur them.
- **Forgetting that rule order matters.** Put specific rules above general ones; first match wins.
