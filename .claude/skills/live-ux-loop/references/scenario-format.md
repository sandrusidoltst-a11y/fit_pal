# Scenario File Format

A scenario file is a **guide for the agent driving the conversation, not a script**. The agent is an LLM playing a real user — it reads the file, understands the goal, and reasons about what to send next based on what the bot replied. The user-side messages in the file are *suggested wording*, not strings to send verbatim.

This matters because the whole reason to have an LLM driver (instead of a traditional record-and-replay test runner) is the agent's ability to *think*. A strict script forces the agent to send messages that may not match the conversational flow — which defeats the purpose. The right model: scenarios capture intent and shape; the agent supplies the lived conversational judgment.

## Why this shape

- **Markdown, not YAML/JSON** — scenarios are read by humans more than they're read by the agent. Markdown stays readable when you skim a directory of past sessions.
- **Suggested wording, not exact strings** — the `User:` line is what a real user *might* say. The agent can rephrase, adapt, skip, or substitute when the conversation calls for it. What stays fixed is the goal of each turn, not its surface form.
- **Goal stays general, not deterministic** — conversations with an LLM-driven bot are non-deterministic. Don't try to assert "bot must reply with exact string X". Detailed scoring lives in `expectations.md` (rubric); the scenario's job is to capture what flow is being exercised and roughly what good looks like at the conversation level.
- **`expect: interrupt | final` describes anticipation, not assertion** — it's the scenario's prediction of what the bot will do at this turn. Divergence between `expect:` and reality becomes a finding (the agent records "expected interrupt, got final"), not a runner failure. The agent reacts to what actually happened, not to what was anticipated.
- **`Resume:` is a hint, not a fixed string** — when the bot interrupts, the agent uses `Resume:` as a starting point, but adapts if the interrupt is about something the scenario didn't anticipate (e.g., interrupt asks for an edit, scenario hint was a plain confirmation).
- **`Probes for:` (optional, recommended) — captures the turn's intent** — letting the agent rephrase the message while still hitting the goal. Especially valuable for probe turns that exist to check a specific behavior.
- **`Dimensions:` field** — anchors which dimensions in `expectations.md` this scenario exercises. Used by scoring (Step 4) to focus on what matters for this scenario.

## Format

```markdown
## Scenario: <short slug-friendly title>
**Goal:** <one sentence, general, not deterministic — e.g., "should log the food correctly and answer the remaining-protein question">
**Dimensions:** <comma-separated dimensions from expectations.md>

1. User: "<suggested message text>"
   Probes for: <intent of this turn — what the agent is trying to elicit/test>
   *(expect: interrupt)*
   Resume: "<suggested resume reply>"
2. User: "<next suggested message>"
   *(expect: final)*
```

### Per-scenario fields

| Field | Required | Purpose |
|---|---|---|
| `## Scenario: <title>` | yes | Title becomes the slug for handoff records, commit messages, report sections. Keep short and descriptive. |
| `**Goal:**` | yes | One sentence, general. *"should log the food correctly", "should answer carb-budget question without inventing data"*. **Not** a deterministic assertion — the detailed evaluation lives in `expectations.md`. |
| `**Dimensions:**` | yes | Which dimensions from `expectations.md` this scenario exercises. Used to focus the scoring step on the dimensions that matter for this scenario. |

### Per-turn fields

| Field | Required | Purpose |
|---|---|---|
| `User: "<text>"` | yes | **Suggested** user-side message — what a real user *might* say. The agent can rephrase or adapt for context. Use whatever language matches what a real user would say (Hebrew, English, mixed). Quotes are conventional but not parsed strictly. |
| `Probes for: <intent>` | optional but recommended for probe turns | One short line describing what this turn is *testing* — e.g., *"did the bot reference time-of-day in its prior reply? if not, push to surface it"*. Lets the agent adapt the message wording while still hitting the goal. Especially useful when the suggested `User:` text only makes sense conditionally. |
| `*(expect: interrupt \| final)*` | yes | The scenario's **anticipation** of what the bot will do here. `interrupt` → expected to pause for HITL; `final` → expected to emit a final reply with no resume needed. The agent reacts to what actually happens; divergence becomes a finding, not a runner failure. |
| `Resume: "<text>"` | only when `expect: interrupt` | **Suggested** resume reply when the bot interrupts. The agent adapts if the interrupt is about something the scenario didn't anticipate (e.g., interrupt requests an edit, hint was a plain confirmation). Skip the field when `expect: final`. |

### How the agent uses these fields

The agent's per-turn loop is roughly:

1. **Read the bot's prior reply** (or detect the bot is at an interrupt).
2. **Look at the next turn's `Goal:` + per-turn `Probes for:` (if any) + suggested `User:` text** to understand what to test.
3. **Decide the message to send** — either the suggested text verbatim, a rephrase that fits the conversational flow, or a substitute that better probes the goal. If the prior reply already settled this turn's question, the agent may skip and move to the next turn (recording why).
4. **Send the message** (or `Resume:` if the bot was at an interrupt).
5. **Record any divergence from `expect:`** — if the scenario said `final` but the bot interrupted, that's a finding plus the agent has to handle the interrupt with an adaptive resume.

The agent records its conversational decisions (what it sent, what it skipped, what it adapted, why) in the run's `transcript.md` so the user can later see the path the agent actually walked.

## Examples

### Single-turn (no HITL)

```markdown
## Scenario: empty-day greeting
**Goal:** when no logs exist for today, bot should open with a coach voice (greet + reference target + invite first meal)
**Dimensions:** empty-log-opener, language-consistency, coach-voice

1. User: "היי"
   *(expect: final)*
```

### Multi-turn with HITL and a probe

```markdown
## Scenario: log breakfast and ask remaining protein
**Goal:** should log the food correctly and then answer the remaining-protein question with a sensible budget computation
**Dimensions:** budget-reasoning, plan-reference, language-consistency

1. User: "אכלתי 100 גרם חזה עוף"
   *(expect: interrupt)*
   Resume: "כן אישור"
2. User: "כמה חלבון נשאר לי?"
   Probes for: does the bot compute remaining = target − consumed instead of restating absolutes? does it condition on time-of-day?
   *(expect: final)*
```

### Edit-during-confirmation

```markdown
## Scenario: edit amount during HITL
**Goal:** should accept an in-confirmation amount edit and re-show the corrected preview before committing
**Dimensions:** hitl-clarity, edit-handling

1. User: "אכלתי 100 גרם פסטרמה"
   *(expect: interrupt)*
   Resume: "תשנה ל-200 גרם"
   *(expect: interrupt)*
   Resume: "כן"
2. *(no User turn — the conversation ends after the confirmation commits and the bot emits its final reply)*
```

(The "edit then re-show" pattern means a single `User:` turn can produce multiple sequential `expect: interrupt` / `Resume:` pairs. The runner treats each `Resume:` as another `command={"resume": ...}` call against the same thread.)

## What `Goal` is *not*

- Not a deterministic assertion: ❌ *"bot replies with exactly: 'logged 100g chicken'"*
- Not a list of acceptance criteria: ❌ *"bot must include calories, must reference plan, must use Hebrew, must..."*

That level of detail belongs in `expectations.md` as a rubric per dimension. The scenario `Goal` is the human-readable purpose — *"this is what we're checking"* — not the evaluator's checklist.

## Common pitfalls

- **Treating `User:` lines as a fixed script.** They're suggested wording the agent can adapt. If you find yourself writing brittle messages that only make sense in one specific reply path, you're scripting — pull back and write looser wording plus a `Probes for:` line that captures the intent.
- **Forgetting `expect:` on a turn.** Every turn needs it. The agent uses it to know whether the bot was anticipated to pause or not, so divergences become findings.
- **Adding a `Resume:` after `expect: final`.** A final reply means the conversation moves on — there's nothing to resume. If you intended another HITL pause, the prior `expect:` should have been `interrupt`. (Adaptive note: if the bot unexpectedly *does* interrupt despite `expect: final`, the agent records the divergence and improvises a resume — but you don't pre-write one.)
- **Putting deterministic copy assertions in `Goal` or `Probes for:`.** That's `expectations.md`'s job. Keep both general.
- **Listing dimensions that aren't in `expectations.md`.** The dimensions field must reference dimensions defined there; otherwise the scoring step has nothing to evaluate against.
- **Over-specifying `Probes for:`.** It's a one-line intent, not a checklist. *"Probes for: did the bot reference time-of-day?"* is good. A four-bullet rubric belongs in `expectations.md`.
