---
name: live-ux-loop
description: Dogfood the FitPal bot end-to-end by acting as a real user against the live LangGraph dev server, OR help the user author the input files (`scenarios.md`, `expectations.md`) that drive a UX loop. Use when the user wants to evaluate bot UX (tone, plan reasoning, language consistency, HITL clarity, budget math), validate prompt/code changes against scripted scenarios, iterate on the bot's behavior without running the full Telegram stack, or build/edit the scenario or expectations files for a future UX loop session. Trigger phrases include "dogfood the bot", "live UX loop", "test the bot UX", "let's chat with FitPal", "run the UX scenarios", "create a scenarios file", "draft scenarios for X", "build expectations file", "add a scenario for the empty-day flow", or whenever the user describes wanting to drive the agent through a user-facing flow, observe replies, or author the inputs that define that flow.
---

# Live UX Loop

This skill drives FitPal as if you were a real user — connecting to the local LangGraph dev server, sending messages, reading replies, handling HITL interrupts, and grounding everything in user-visible text. It's the foundation for closing the gap between "the prompt looks right in the editor" and "the bot actually feels good to talk to".

## Modes

The skill has two modes. Pick the right one based on the user's intent at the start of the session.

### Mode A — Run the loop (default)

The user wants to dogfood the bot against an existing set of scenarios and expectations. This is the main mode and what the rest of this SKILL.md describes (Setup → Eval bookends → After-conversation pipeline → Routing findings → Regression → Report).

Trigger when the user says things like *"run the UX loop"*, *"dogfood the bot"*, *"let's test these scenarios"*, *"chat with FitPal and see how it goes"* — anything that describes driving the bot, not authoring inputs.

### Mode B — Create input files

The user wants to author or edit the input files that *drive* a future UX loop session. Same skill, different output: instead of running conversations and producing findings, you produce a markdown file in the canonical format.

Trigger when the user says things like *"create a scenarios file"*, *"draft scenarios for the empty-day flow"*, *"add a scenario for confirming with edit"*, *"build expectations file"*, *"help me write expectations for tone and budget reasoning"*. See [Creating input files](#creating-input-files) below for the full flow.

### When the user's intent is ambiguous

Ask. *"Are we running the loop today or building scenarios/expectations?"* — one short question. Don't guess. The two modes are different jobs and starting in the wrong one is wasted work.

## Scope

The skill covers the transport layer, core principles, eval bookends (baseline at start + regression check at end via the `langsmith-evaluator` skill), the after-conversation analysis pipeline (scoring against expectations, trace inspection via the `langsmith-trace` skill, DB verification via Supabase MCP, bug attribution), routing of findings (prompt/copy bugs fixed in-loop on a session branch, code bugs persisted as structured handoff records), regression eval gating, and PR mechanics. The loop never patches code, never invokes any planning or fix-it skill on the handoff records, and the PR is gated on no eval regression. The user picks up handoff records in a separate session, on their own cadence.

A session runs against **one scenario file and one expectations file**, both per-session inputs the user maintains.

## Why this exists

The bot's UX bugs (tone, missing budget reasoning, language leaks, HITL copy issues) are mostly invisible until you actually chat with the bot. Static evals catch some of it but miss the lived feel of a conversation. Manual dogfooding catches everything but is slow and you forget what was wrong by the time you sit down to fix it.

This skill closes that loop: agent talks to the bot like a user, agent (with full project context) judges what's wrong, agent fixes it. The agent has more context than an LLM-judge — it can read `docs/nutrition-method.md`, the prompts, the schemas, and reason about whether a reply breaks the *spirit* of the coaching method, not just a checklist.

## Setup

### Dev server (LangGraph)

The skill connects to `http://127.0.0.1:2024`. The server health endpoint is `/ok`.

Mirror the auto-start pattern from `tests/graph_api/conftest.py`:

1. Probe `GET /ok` with a short timeout. If it returns 200, server is up — proceed.
2. If not running, start it: `uv run langgraph dev --port 2024 --no-browser` in the background.
3. Poll `/ok` every 2 seconds until ready (cap the wait — first cold start can take ~60s).
4. If startup hangs, the most common cause is an orphaned process holding the port. See `docs/orphaned-langgraph-server.md` for the kill recipe.

The server uses `langgraph.json` (dev config — no auth, exposes `fitpal` graph). Do not use `langgraph.production.json` — that requires the shared-secret middleware and is meant for Railway.

### Cleanup — leave no orphans

When the skill's work is done, the dev server must not be left running. Long-lived `langgraph dev` processes are the most common source of "port 2024 already in use" pain in this repo (see `docs/orphaned-langgraph-server.md`).

Rule: **only kill the server you started.** Track that explicitly:

1. At setup, before probing `/ok`, record whether the server was already running (`server_was_pre_existing = is_server_running()`).
2. If it was already running, leave it alone — the user has another terminal open with `langgraph dev`, and killing it would surprise them.
3. If you started the server (`server_was_pre_existing` was False), kill it before returning. Use the same recipe as `tests/graph_api/conftest.py:cleanup_server`:
   ```bash
   # macOS / Linux
   kill $(lsof -t -i:2024) 2>/dev/null
   ```
   Then verify with a final `/ok` probe — if it still answers 200, escalate (something else may have respawned it; surface to the user, don't loop).
4. Do this in a finally-style block so cleanup runs even if the scenario errored out mid-run. A crashed scenario must not leak a server.

If the user explicitly asks the skill to leave the server running (for them to keep poking at it manually after), respect that — but state out loud what you're leaving behind so they don't forget.

### Dev user

Every run must include the dev user's `user_id` so context flows correctly into the graph (FK to `auth.users`, RLS policies, profile lookup, daily log injection). Use the same user the graph-api tests use:

```python
USER_CTX = {"user_id": "72c10336-9d61-4357-9851-20cbb4d32b1a"}
# auth.users entry: e2e@test.fitpal.bot
```

Pass `context=USER_CTX` on **every** `runs.stream(...)` call — both initial messages and interrupt resumes. Skipping it falls back to `DEFAULT_DEV_USER_ID` and silently mixes data across users.

This user is shared with `tests/graph_api/`, so its DB state (daily log, profile, plan) is whatever the test suite last left there. That's fine for UX evaluation — what matters is the bot's reasoning over whatever state exists, not the state itself. If a scenario needs a clean slate, surface that to the user; don't silently delete data.

## Interaction primitives

### Connect

```python
from langgraph_sdk import get_client

client = get_client(url="http://127.0.0.1:2024")
thread = await client.threads.create()
thread_id = thread["thread_id"]
```

A thread is one conversation. Create a new one per scenario; reuse it across turns within a scenario.

### Send a user message (turn 1, or any non-resume turn)

```python
final = None
async for chunk in client.runs.stream(
    thread_id, "fitpal",
    input={"messages": [{"role": "user", "content": "<user text>"}]},
    context=USER_CTX,
    stream_mode="values",
):
    if chunk.event == "values":
        final = chunk.data
```

After the stream finishes, `final` is the last graph state. The bot's reply lives in `final["messages"]` as the most recent `type=="ai"` entry. **Read only that** — that's what the user sees.

### Detect whether the bot paused for HITL

```python
state = await client.threads.get_state(thread_id)
interrupts = [
    it.get("value")
    for t in (state.get("tasks") or [])
    for it in (t.get("interrupts") or [])
]
is_paused = bool(interrupts)
```

If `is_paused`, the bot is waiting for a confirmation/edit/rejection. Use the interrupt's `value` dict (described below) instead of looking for an AI message — there won't be one until the interrupt resolves.

### Resume an interrupt

```python
final = None
async for chunk in client.runs.stream(
    thread_id, "fitpal",
    command={"resume": "<user reply, e.g. 'yes' or 'change chicken to 200g'>"},
    context=USER_CTX,
    stream_mode="values",
):
    if chunk.event == "values":
        final = chunk.data
```

After resuming, re-check the interrupt state — the graph may pause again (e.g., after an edit) or it may complete and emit a final AI message.

## Reading the interrupt dict (no formatter needed)

The interrupt's `value` dict — emitted by `confirmation_node._build_interrupt_payload` — looks like this:

```json
{
  "question": "רגע, בוא נוודא שתפסתי נכון לפני שאני שומר:",
  "items": [
    {
      "index": 0,
      "description": "חזה עוף מבושל — 100.0g",
      "calories": 165.0,
      "protein": 31.0,
      "carbs": 0.0,
      "fat": 3.6,
      "source": "database",
      "servings": 1.33,
      "category": "protein"
    }
  ],
  "totals": {"calories": 165.0, "protein": 31.0, "carbs": 0.0, "fat": 3.6}
}
```

**What the real Telegram user sees** — the `bot/gateway.py:_format_interrupt_value` function expands this dict into a formatted message, but the underlying user-visible text is:
- `value["question"]` — the confirmation prompt verbatim
- `value["items"][i]["description"]` — what the user reads as the food line (verbatim string the gateway uses)
- The macros + servings + category get rendered into a human-readable block, but the *content* is exactly these fields

You don't need to import or replicate the gateway formatter. You can read the dict directly and judge UX from the strings + structured fields. In fact, reading the dict gives you *more* diagnostic power than the rendered string — you see `source`, `category`, `servings`, and any FAILED items, which lets you reason about *why* the bot did what it did, not just what the user saw.

### What's user-visible vs diagnostic

| Field | User-visible? | Use for |
|---|---|---|
| `question` | yes (verbatim) | Judging confirmation copy, language consistency |
| `items[].description` | yes (verbatim) | Judging item rendering — e.g., "100.0g" vs "2 פרוסות" (Important #5: HITL drops natural units) |
| `items[].calories/protein/carbs/fat` | yes (formatted) | Judging macro accuracy + display polish |
| `totals` | yes (formatted) | Same |
| `items[].source` | no — diagnostic only | Tells you if item came from DB or LLM estimation. Useful for explaining surprising macros. |
| `items[].category`, `items[].servings` | no — diagnostic only | Tells you how the item slots into plan-vs-actual math. |
| `processing_result` (if present in state) | no — diagnostic only | FAILED items with error messages (UNIT_MISMATCH, etc.) — explains *why* the bot is asking what it's asking. |

## Core principles

### Principle 1: Mid-conversation, see only what a user sees

When you're driving the conversation, your inputs to "what should I send next" are exactly what a Telegram user would have:
- The bot's last AI message text, **or**
- The interrupt's `question` + `items[].description` strings

Do not peek at internal state, the prompt, the parsed action, or the trace mid-conversation. That's x-ray glasses — the moment you do it, you stop reacting like a user and start gaming the answer key. The failure modes you're trying to catch are exactly the ones a user would feel; if you can see through them, you can't catch them.

The one transport-level exception is the interrupt-detected flag (`is_paused` above). That's a turn-boundary signal, not content — you need it to know when the bot is waiting for you vs when it has emitted a final reply.

### Principle 2: State and trace analysis happen *after* the scenario, not during

After the scenario ends (the conversation reaches a natural stopping point or the bot emits a final AI message that doesn't invite a reply), then read everything: the full LangSmith trace, intermediate node outputs, structured-output payloads, and the actual DB state. That's where "is this a prompt bug or a code bug?" gets answered.

This separation matters because dogfooding and diagnosis are different jobs. Mixing them produces both worse user-perspective signals (you over-reach into reasoning the user can't see) and worse diagnostics (you write findings before you know what the conversation actually felt like).

The mechanics for this phase live in [After the conversation](#after-the-conversation) below.

### Principle 3: Inputs are user-maintained

Two files belong to the user, not the agent:

**`scenarios.md`** — the user-side flows to drive. Plain text, in whatever language matches the scenario (Hebrew, English, mixed). The *content* (which scenarios you run on a given session) is per-session. The *shape* is defined by the skill so the runner can parse it deterministically — see `references/scenario-format.md` for the full spec, including required fields, per-turn `expect: interrupt | final` markers, and the rule that scenario `Goal` stays high-level (detailed evaluation lives in `expectations.md`, not in scenario assertions).

Quick example:

```markdown
## Scenario: log breakfast and ask remaining protein
**Goal:** should log the food correctly and then answer the remaining-protein question
**Dimensions:** budget-reasoning, plan-reference, language-consistency

1. User: "אכלתי 100 גרם חזה עוף"
   *(expect: interrupt)*
   Resume: "כן אישור"
2. User: "כמה חלבון נשאר לי?"
   Probes for: does the bot compute remaining = target − consumed instead of restating absolutes?
   *(expect: final)*
```

**`expectations.md`** — the rubric, the regression thresholds, and the runtime behavioral rules, all in one file. Three sections per the format spec at `references/expectations-format.md`:

1. **Dimensions** — what to evaluate per scenario and how (pass/fail rules, scoring rubrics, checklists, etc. — user picks the shape per dimension). Pulled from `docs/nutrition-method.md` (coach voice, plan structure, free-calorie rules) plus the user's preferences for tone, language consistency, time-awareness, HITL clarity, and anything else they care about.
2. **Regression thresholds** — per-metric tolerances for the Step 7 eval comparison (e.g., `correct_dates: max -2pp`, `food_name_quality: no drop`).
3. **Behavioral rules** — runtime decisions triggered by dimension scores, `expect:` divergences, trace signals, or timeouts (e.g., *"if `tone` scores below 2 → record finding, abort scenario"*).

These three responsibilities live together because they all reference the same dimensions by name and need to stay in sync. Splitting them invites drift between rule and rubric. The user maintains this file — the agent reads it, doesn't write to it (except in Mode B, with explicit approval).

Note: the eval baseline (Step 0) is **not** a file. The user names it in chat at session start — either an eval to run fresh or an existing experiment to read. See Step 0 for the mechanics.

The agent does not invent scenarios or expectations. If the user wants the agent to draft new ones, that's a separate request — the agent proposes, the user approves and commits to the file.

Both files live under the loop's input folder: `tests/ux-loop/<loop-name>/inputs/scenarios.md` and `tests/ux-loop/<loop-name>/inputs/expectations.md`. See Step 8 for the full directory structure.

## Eval bookends — baseline at start, regression check at end

The in-loop fix path mutates prompts. Without a known-good reference and a regression gate, one fix can silently regress a different dimension and ship in the same PR. Real evals — the LangSmith experiments in `notebooks/evals/` — are the regression guardrail.

### Step 0: Baseline (before any conversations run)

Before the first scenario starts, capture a baseline so the regression check at the end has something to compare against.

**The user names the input in chat at session start.** This step does not auto-select evals and there is no `evals.md` file. The user provides one of two things:

- **(a) An eval to run fresh** — e.g., *"run `eval_input_parser_hebrew`"*. **Trigger the `langsmith-evaluator` skill** to execute it and capture the resulting scores as baseline.
- **(b) An existing LangSmith experiment to read** — e.g., *"use experiment `input-parser-hebrew-gpt-5.4-mini-cc6bb8c5` as baseline"*. Fetch that experiment's existing results from LangSmith instead of re-running anything. Faster, and avoids LLM-variance-only "regressions" that come from running the same eval twice with no code change.

If the user hasn't named either at session start, **ask** before proceeding. Do not default to "run everything matching `expectations.md`" or "skip the baseline" — both fail silently in different ways.

If a dimension declared in `expectations.md` has no eval covering it, call out the gap explicitly: *"`expectations.md` declares budget reasoning, but no eval covers it. Regression on this dimension is only testable by re-running the scenario itself."* Don't paper over it.

If a freshly-run baseline (mode a) fails or returns flaky results, **stop and surface to the user.** Proceeding on noisy baselines makes the regression check meaningless.

### Step 7: Regression eval (after the loop, before the PR)

If the session produced any prompt/copy commits (in-loop fixes from Step 6), re-run the same eval set captured at baseline. Compare scores per metric.

**Regression threshold is user-defined**, declared per metric in `expectations.md` (e.g., `correct_dates: max -2pp`, `food_name_quality: no drop`). LLM-as-judge metrics carry natural run-to-run variance; the threshold accounts for it.

| Outcome | Action |
|---|---|
| All metrics within threshold of baseline | PR is unblocked. Note baseline → final scores in the session report. |
| Any metric regressed beyond its threshold | **Block the PR.** Surface to the user with: which metric, by how much, baseline → final, and which fix commits could plausibly explain it. Let the user decide: revert the suspect commits, accept the regression, or hand off to deeper investigation. |
| Eval run itself fails / inconclusive | Block the PR for the same reason as a noisy baseline. Surface and pause. |

If the session produced **no prompt commits** (everything was a handoff, or the loop found nothing to fix), skip the regression run — there's nothing to regress against the baseline.

The regression check happens **before** the findings report (Step 8) so the report can include before/after eval scores, not just per-scenario judgments.

## After the conversation

Once the scenario reaches a natural stop (the bot emits a final AI message that doesn't invite a reply, or the user-side script has run all its turns), the agent moves into analysis mode. This is a strict pipeline — each step has a single job, and they must run in order.

### Step 1: Capture the transcript

You already have it from the loop. The transcript is exactly what was visible to you while playing the user — the user messages you sent, the bot's AI replies, and the rendered interrupts (`question` + per-item `description`). Keep this in memory; it's input to the scoring step.

### Step 2: Fetch the trace

The thread_id you got from `client.threads.create()` at scenario start is the same UUID LangSmith uses to group all runs from that conversation. LangGraph propagates it automatically when `LANGSMITH_TRACING=true` is set server-side (it is, in this repo's `.env`). One scenario = one thread = one cleanly-scoped batch of traces. The skill never has to correlate run-ids manually — just remember the thread_id.

**Trigger the `langsmith-trace` skill** for trace fetching. It already knows the CLI, env setup, the `thread get` vs `trace get` distinction, and exporting full trace data. Don't reimplement those mechanics here — invoke the skill with the thread_id and let it return the data.

For human-readable rendering when you need to skim a single thread, `src/scripts/print_trace.py` is the repo-local viewer. Use it as a fallback or when you want compact output for a finding writeup.

### Step 3: Verify DB state — mandatory, via Supabase MCP

This step is **not optional**. Every scenario produces some claim about persistence ("logged 100g chicken", "no entries today", "weight updated to 74kg"), and a bot can sound right while writing the wrong thing — or claim nothing happened while a row landed anyway. The DB is the only source of truth.

Use the **`supabase` MCP server** (declared in `.mcp.json`, documented in `CLAUDE.md`). For each scenario, query the tables touched by the conversation:

| Scenario type | Tables to check | What to verify |
|---|---|---|
| Food log (LOG_FOOD) | `daily_logs`, `food_items` | New row exists for `user_id`, with `food_id`, `amount_g`, `timestamp`, calories/macros matching what the bot claimed. If `source: "estimated"`, also verify `food_items` row was created. |
| Stats query (QUERY_DAILY_STATS) | `daily_logs` | Bot's claim about what's logged matches actual rows for the queried date(s). |
| Personal stats (LOG_PERSONAL_STATS) | `personal_stats_log` | New row exists for the right metric (weight / body_fat) with correct value + timestamp. |
| Plan reference | `user_profiles` | The plan the bot is reasoning over matches `nutrition_plan` for that user_id. |

**Read-only queries only.** Per project rules (`feedback_no_db_mutations_without_permission`), never DELETE/UPDATE/INSERT. If a scenario needs DB cleanup or seeding, surface that to the user — don't do it silently.

Always scope queries by `user_id = '72c10336-9d61-4357-9851-20cbb4d32b1a'` (the dev user). Cross-user contamination is the whole reason RLS exists; replicate that discipline at the query level.

### Step 4: Score the conversation against `expectations.md`

**The user owns the evaluation method, not just the criteria.** `expectations.md` declares both:

- **What to evaluate** — the dimensions (tone, plan reference, language consistency, budget reasoning, time awareness, HITL clarity, anything else the user cares about).
- **How to evaluate it** — for each dimension, the user defines the judgment process. That can take any shape that fits the dimension: a pass/fail rule, a 0-3 scoring rubric with anchors, a checklist of sub-criteria all of which must hold, examples of "this counts as a pass / this counts as a fail", a weighting scheme combining sub-criteria, or even a "consult `docs/nutrition-method.md` section X" pointer. Different dimensions can use different methods.

The skill enforces only the **output structure** of the per-dimension verdict (below); it never invents the metric, the rubric, the threshold, or the judgment process. If a dimension is declared without a "how to evaluate" — i.e., only the dimension name with no method — flag it back to the user and don't score it. Defaulting in silence produces wrong-but-confident reports.

This is also where per-scenario customization lives: a scenario in `scenarios.md` may need a stricter or different rubric than the global default (e.g., an empty-log scenario needs a specific check on coach-voice opener). The user can declare scenario-specific overrides inside `expectations.md` or alongside the scenario — the skill respects whatever the user wrote.

For each dimension declared with an evaluation method, produce:

- **Verdict**: `pass` / `fail` / `n/a` (n/a when the scenario didn't exercise this dimension). If the user's method outputs a numeric score, also include the score.
- **Severity** (only on `fail`): `low` / `med` / `high`. Low = polish, high = blocks the user from accomplishing the task.
- **Reasoning**: 1-3 sentences citing specific evidence from the transcript or trace. No vague "tone could be better" — quote the line, point at the field.

### Step 5: Attribute every failure to a bug bucket

For each `fail` from step 4, classify it into exactly one bucket. The bucket determines where to look for the fix:

| Bucket | Symptom | Trace signal | Fix lives in |
|---|---|---|---|
| **Conversation-only** | Wrong wording, language leak, awkward phrasing, formatting bug | Trace shows the model produced this string by choice — context was fine | `prompts/*.md` (mostly `response_generator.md`), `src/i18n/*.yaml`, or gateway copy |
| **Reasoning** | Right context arrived, bot ignored or misused it (e.g., budget reasoning skipped while plan + log were injected) | Trace's `response_node` LLM call shows the prompt + context contained what was needed; reply doesn't reflect it | Prompt — usually `prompts/response_generator.md` |
| **Pipeline** | Wrong context arrived (action misclassified, daily log missing, food not found, dates lost across nodes) | Trace shows wrong `action`, missing `daily_log_today`, FAILED `processing_result`, or wrong sub-state in `log_food` / `query_stats` | Code (`src/agents/nodes/*.py`, `src/context.py`, `src/services/*.py`) and sometimes `prompts/input_parser.md` |
| **State/DB** | Bot's reply diverges from DB reality (claimed it logged X, DB has Y; said "nothing today", DB has rows) | DB query (step 3) contradicts the bot's claim | `commit_node`, `daily_log_service`, query helpers, or schema/timezone bugs |

Use exactly one bucket per failure. If a bug spans buckets ("the reply is awkward AND the data was wrong"), split it into two findings — one per bucket. This keeps fix paths clean.

For each finding, name the most likely fix location (file + roughly where), but do not propose a patch. The patcher is a later phase.

### Step 6: Act on findings — route each by bucket

Different bugs have different fix profiles. The skill routes each finding by its bucket from Step 5. **Prompts and copy stay in the loop. Logic changes get handed off.** The line is drawn by responsibility, not by size.

| Bucket | Action |
|---|---|
| **Conversation-only** (`prompts/*.md`, `src/i18n/*.yaml`, `bot/gateway.py` `MESSAGES` constants) | **Fix in-loop** |
| **Reasoning** (prompt edits, mostly `response_generator.md`) | **Fix in-loop** with re-test discipline |
| **Pipeline** (code in `src/agents/nodes/`, `src/services/`, `src/context.py`) | **Handoff record only — never patch** |
| **State/DB** (`commit_node`, services, query helpers, schema) | **Handoff record only — never patch** |

The compound-context advantage (you've just built deep understanding of these bugs through the conversation + trace + DB analysis) compounds most on prompt iteration, where the natural workflow *is* "edit → re-run → did it improve?". For logic changes, that same context is gold — but the patching itself belongs in a separate session under whatever planning discipline the user prefers (e.g., `plan-feature`). The live-ux-loop skill never invokes that flow; it just persists the context for later.

#### In-loop fix path (Conversation-only and Reasoning buckets)

1. **Branch hygiene** — work on `ux-loop/<YYYY-MM-DD>` (or per-session). Never on main. If the branch doesn't exist yet, create it from main at the start of the session.
2. **One commit per finding** — keeps the diff reviewable per-bug. Commit message references the finding (the dimension that failed + the scenario).
3. **Re-run the scenario that surfaced the bug** — must pass after the fix. Use the same loop mechanics (Steps 1-5 above) on the fixed code. If it still fails, increment the attempt counter; do not silently move on.
4. **Iteration cap per finding** — 3 prompt attempts max. If still failing on attempt 3, demote it to a handoff record (the bug is deeper than copy; logic is involved). Do not loop indefinitely.
5. **PR at session end** — single PR off the session branch with all in-loop fixes. Each commit reviewable on its own.

#### Handoff path (Pipeline and State/DB buckets)

The agent does not patch. It writes a **handoff record** containing:

- Bucket label + suggested fix location (file + roughly where, from Step 5)
- The user-visible conversation transcript for the failing scenario
- The relevant trace excerpts — specific node call, specific input/output that demonstrates the bug
- DB state evidence (the actual rows queried via Supabase MCP) if state/DB bug
- Any patterns observed across multiple scenarios in this session (e.g., "same bug surfaced in 3/5 scenarios touching `query_stats`")

That record persists somewhere on disk so when the user picks it up later (in a separate session, with whatever planning skill they choose) the full context is right there, not cold. **No context evaporates** — it gets persisted instead of acted on. The live-ux-loop skill never reads, fixes, or otherwise acts on handoff records. It only writes them.

The on-disk format for handoff records (and for the session-level findings report) is specified in Step 8 below.

#### Mixed-bucket findings

If a finding spans buckets ("the wording was awkward AND the data flow was wrong"), the existing split-per-bucket rule from Step 5 already handles it: the copy half becomes one finding (in-loop fix), the logic half becomes another finding (handoff record). They end up in two places — that's correct, not duplication.

#### When the loop hits a handoff finding mid-session

The loop does not block. It writes the handoff record, logs that the finding was deferred, and continues to the next scenario. At session end you'll have a PR (in-loop fixes) plus a set of handoff records (logic bugs awaiting a separate session). You decide when to tackle the handoff queue and which planning skill to use.

### Step 8: Write the findings report and persist handoff records

A live-ux-loop session is invoked against **one scenario file and one expectations file at a time** — not a batch of scenarios. All session output lives in a single run folder under that scenario's loop directory. The structure is:

```
tests/ux-loop/<loop-name>/
├── inputs/
│   ├── scenarios.md              # the one scenario for this loop
│   └── expectations.md           # rubric + thresholds + behavioral rules
└── runs/
    ├── run1-<short-tag>/
    │   ├── transcript.md         # the conversation as the "user" saw it
    │   ├── findings.md           # structured per-dimension verdicts + bug attributions
    │   ├── handoffs/             # one .md per code-bug handoff (Pipeline / State-DB buckets)
    │   ├── trace.jsonl           # exported LangSmith trace for the thread
    │   ├── db-snapshot.md        # DB state captured during Step 3
    │   └── eval-scores.json      # baseline (Step 0) + final (Step 7) eval scores
    ├── run2-<short-tag>/
    └── ...
```

#### Folder semantics

- **`<loop-name>`** is the canonical name of this UX loop — typically the scenario's slug (e.g., `empty-day-greeting`, `log-yesterday-flow`). Stable across runs. Multiple runs against the same loop track its evolution as the bot/prompts change.
- **`inputs/`** is stable across runs of the same loop. The user changes inputs only when the scenario itself changes meaning. Run-to-run iteration mutates prompts/code, not inputs.
- **`runs/run<N>-<tag>/`** is one folder per `live-ux-loop` session.
  - `<N>` auto-increments. Read existing run folders in `runs/` to compute the next N.
  - `<tag>` is a short user-provided slug describing what changed for this run: `baseline`, `tone-fix`, `after-budget-prompt-edit`, `regression-check`. The agent prompts for the tag at session start.
  - Even if a session does multiple in-loop fix attempts on the same scenario, that's one run — the attempts are commits on the branch, not separate run folders. A new session = a new run folder.

#### Per-run files

| File | Required | Contents |
|---|---|---|
| `transcript.md` | yes | The conversation chronologically — user message → bot reply (or rendered interrupt) → next message. The "user-visible" view, no internal state. |
| `findings.md` | yes | Per-dimension verdicts from Step 4 (verdict + severity + reasoning), per-finding bug attribution from Step 5 (bucket + suggested fix location), session summary at top (scenario name, run tag, baseline → final eval delta). |
| `handoffs/<finding-slug>.md` | only when Pipeline or State-DB findings exist | One file per code-bug handoff record. Contents per Step 6's handoff path: bucket label, suggested fix location, transcript excerpt, trace excerpts, DB evidence, cross-scenario patterns. |
| `trace.jsonl` | yes | The exported LangSmith trace for the thread (Step 2). One run per line. |
| `db-snapshot.md` | yes | DB state captured during Step 3 — the queries run via Supabase MCP and their results, scoped to the dev user. |
| `eval-scores.json` | yes when evals were run | Baseline (Step 0) + final (Step 7) scores, per metric. JSON shape: `{"baseline": {...metric: score...}, "final": {...metric: score...}, "deltas": {...metric: delta...}, "regression_threshold_status": {...metric: pass\|fail...}}`. |

#### Naming and slugs

- Loop names: lowercase, hyphens for spaces, no special characters. Match the scenario's slug from `## Scenario:` heading where possible.
- Run tags: same conventions, ≤30 chars. Descriptive of *what changed*, not what happened.
- Handoff record filenames: `<finding-slug>.md` where the slug matches the finding's identifier in `findings.md`.

#### Commit policy

**Commit everything.** Inputs and run output both go to the session branch (`ux-loop/<date>`) and into the PR. No `.gitignore` for these paths. Rationale: cross-run history is valuable for trending, and selectively gitignoring trace dumps adds drift risk that's worse than the storage cost.

**CI/CD safety**:
- **CD is already safe**: `.github/workflows/cd.yml` uses a path filter that excludes `tests/ux-loop/**`. PR merges containing only ux-loop output do not trigger Railway redeploy. PRs that *also* edit `prompts/*.md` will trigger CD on merge — that's correct, prompt changes should deploy.
- **CI**: runs on every push/PR by default. Tests in `tests/unit/`, `tests/integration/`, `tests/graph_api/` are explicitly scoped — they don't recurse into `tests/ux-loop/`, so adding files there won't fail CI. CI will *run* (~1-2 min wasted), but it won't fail. The user may add a `paths-ignore` for `tests/ux-loop/**` to CI's triggers separately; that's a workflow-file edit outside this skill's scope.

### Step 9: Push the branch and open the PR

**Invoking `live-ux-loop` is the user's explicit authorization for the whole pipeline — including `git push` and `gh pr create`.** The agent does not pause at session end to ask for confirmation. The contract is set at session start: run the loop, produce findings, apply in-loop fixes if any, push, open PR. This is the one place this skill explicitly overrides the project's general "never push without explicit permission" rule, because the skill's invocation *is* the explicit permission.

#### Branch naming

`ux-loop/<loop-name>-<YYYY-MM-DD>` for the first session of the day on a given loop.

For same-day re-invocations on the same loop, append `-r2`, `-r3`, etc. — the agent reads existing branches and computes the next suffix.

Examples:
- `ux-loop/empty-day-greeting-2026-05-08`
- `ux-loop/empty-day-greeting-2026-05-08-r2` (second session same day)
- `ux-loop/log-yesterday-flow-2026-05-08`

Branches always come off the latest `main`. No long-running ux-loop branches.

#### PR title

Conventional-commit style, scoped by loop name:

```
ux(<loop-name>): <one-line summary of what changed>
```

Examples:
- `ux(empty-day-greeting): tighten coach voice and add remaining-budget template`
- `ux(log-yesterday-flow): no fixes — recorded 2 code-bug handoffs`

If the session landed no prompt commits (handoffs only), say so in the title. Don't fake a "fix" summary.

#### PR description body

Use this template:

```markdown
## Summary
<2-3 sentences: what scenario was tested, what changed, what the eval delta was>

## Run folder
[`tests/ux-loop/<loop-name>/runs/run<N>-<tag>/`](relative-link)

## Fixes applied (in-loop)
- `<commit hash short>` — <commit message subject>
- `<commit hash short>` — <commit message subject>

(Or: "_No prompt fixes applied this session._")

## Eval delta (Step 7)
| Metric | Baseline | Final | Δ | Threshold | Status |
|---|---|---|---|---|---|
| `<metric>` | 0.91 | 0.91 | 0 | max -2pp | ✅ within |
| `<metric>` | 0.85 | 0.83 | -2pp | max -3pp | ✅ within |

(Or: "_No evals run this session._")

## Outstanding handoffs (for separate sessions)
- `handoffs/<finding-slug>.md` — <one-line description>
- `handoffs/<finding-slug>.md` — <one-line description>

(Or: "_No code-bug handoffs from this session._")

## Test plan
- Findings report: `runs/run<N>-<tag>/findings.md`
- Eval scores: `runs/run<N>-<tag>/eval-scores.json`
```

#### Sessions with no prompt fixes

If the session ended with zero in-loop fix commits (all findings were Pipeline / State-DB → handoff records, or no findings), **still open a PR** with the run folder. The findings + eval scores + handoff records are durable history regardless of whether anything was patched. The PR title makes it explicit ("_no fixes — recorded N handoffs_").

This rule keeps the on-disk format consistent: every session produces a run folder on main eventually, none get orphaned on unmerged branches.

#### One PR per session

Each `live-ux-loop` invocation = one session = one branch = one PR. Within a session, multiple commits accumulate on the same branch (one per finding fixed, capped at 3 attempts per finding). They all roll into the single session PR.

Multiple PRs only happen across sessions. Re-invoking the skill tomorrow → fresh session → new branch → new PR.

## Creating input files

This is **Mode B** from the Modes section above. The user wants to author or edit one of the user-maintained input files (`scenarios.md` or `expectations.md`) for a future UX-loop session.

The skill that owns the format is the right place to help write files in that format — same logic for both files. The agent never invents content the user didn't describe; it organizes, structures, and surfaces gaps.

### Authoring `scenarios.md`

1. **Read `references/scenario-format.md` first.** Every drafting decision (required fields, `expect: interrupt | final` semantics, `Goal` stays general, dimensions reference `expectations.md`) comes from there. Don't draft from memory.
2. **Read the user's `expectations.md` if it exists.** The `Dimensions:` lines you propose must reference dimensions actually declared there. If `expectations.md` doesn't exist or is empty, surface the gap explicitly: *"`expectations.md` doesn't exist yet, so I can't validate dimension names. Want to draft expectations first, or proceed with placeholder dimensions you'll wire up later?"* — then let the user decide.
3. **Conversational drafting.** Don't generate a wall of scenarios. Per scenario:
   - Ask what flow the user wants to test
   - Propose a one-sentence general `Goal:` (non-deterministic — same rule as the format spec)
   - Walk through turns: ask the suggested user-side message, ask whether they expect `interrupt` or `final`, ask the resume hint if `interrupt`. For probe turns (turns that exist to elicit a specific behavior), capture an optional `Probes for:` line — one short sentence about the turn's intent. This lets the agent rephrase the message at runtime while still hitting the goal.
   - Confirm the dimensions
4. **Show the draft, get approval, then write.** Don't write to disk silently. Show the formatted scenario block in chat, let the user edit, write only after sign-off. Location is the user's call — ask where the file should live (or which existing file to append to).

**Guardrails the skill enforces during drafting**:

- `Goal` stays general. If the user dictates deterministic assertions (*"bot must say exactly 'logged 100g chicken'"*), redirect: *"That belongs in `expectations.md` as a rubric criterion, not in the scenario `Goal`. Let me phrase it generally — does 'should log the food correctly' capture the intent?"*
- `Dimensions:` lines only reference dimensions in `expectations.md`. Don't auto-add a dimension that doesn't exist there. If the user names a new dimension, surface it: *"that dimension isn't in `expectations.md` yet — add it there first, or note it as a TODO?"*
- Never propose scenarios the user didn't describe. If the user says *"draft 10 scenarios"* without specifying, ask what flows they want; don't generate from imagination.

### Authoring `expectations.md`

1. **Read `references/expectations-format.md` first.** The full spec — required sections (Dimensions, Regression thresholds, Behavioral rules), per-dimension required fields, evaluation method shapes, behavioral-rule grammar, common pitfalls — lives there. Don't draft from memory.
2. **Conversational drafting, one dimension at a time.** Per dimension:
   - Ask what the dimension covers (`What:`)
   - Ask the evaluation method — guide the user to one of the shapes in the spec (pass/fail rule, N-point rubric, checklist, weighted sub-criteria, examples-based, external-reference). Don't pick the shape for them; ask.
   - Capture the rubric content (anchors, items, examples)
   - Confirm the output type (`Output:`)
3. **Then regression thresholds.** For each metric the user names, ask the threshold (`max -Npp`, `no drop`, etc.). If the user doesn't know yet, leave the section empty — it's required as a heading but can have zero rules.
4. **Then behavioral rules.** Walk the user through divergence handling (`expect:` mismatches), dimension-score thresholds, trace signals, timeouts. For each rule, capture `when:` and `do:`. Cross-check rule references against the dimensions defined in step 2 — surface any dimension name that doesn't match.
5. **Show the draft, get approval, then write.** Same as scenarios — don't write to disk silently.

**Guardrails the skill enforces during drafting**:

- Every dimension must have an operational `How to evaluate:`. *"Should sound natural"* fails the test; ask for a rubric, checklist, or examples-based shape instead.
- Behavioral rules can only reference dimensions declared in Section 1. If the user proposes a rule citing an undeclared dimension, surface it: *"`hitl-clarity` isn't declared as a dimension yet — add it first, or rewrite the rule to reference an existing dimension?"*
- Don't auto-generate dimensions or rules. Propose, confirm, write. Same rule as scenario authoring: organize, don't invent.
- Dimensions and metrics are different things. Dimensions are scored per-scenario by the agent; metrics come from LangSmith eval runs. They share the regression-threshold mechanic but are populated by different processes — don't blur them when drafting.

### Boundaries between Mode A and Mode B

- Mode B never starts the dev server. No conversations happen, no traces are fetched, no DB is queried. It's a writing session.
- Mode B never edits prompts or code. Its only output is a markdown file in the user's chosen location.
- If the user pivots mid-session ("ok now let's run these scenarios I just drafted"), that's a Mode A request — do the dev server setup fresh, don't try to mix the two flows in one go.

## Don't extrapolate beyond this spec

If the user requests behavior outside what's specified here (e.g., multi-scenario sessions, CI integration, auto-applying handoff fixes, or any new mode), pause and design the new piece together with them rather than improvising. The boundaries of this skill are deliberate — silently expanding scope produces drift between what the user expects and what the skill actually does.

## Quick reference: full single-turn flow

```python
from langgraph_sdk import get_client

USER_CTX = {"user_id": "72c10336-9d61-4357-9851-20cbb4d32b1a"}

client = get_client(url="http://127.0.0.1:2024")
thread = await client.threads.create()
thread_id = thread["thread_id"]

# Send message
final = None
async for chunk in client.runs.stream(
    thread_id, "fitpal",
    input={"messages": [{"role": "user", "content": "אכלתי 100 גרם חזה עוף"}]},
    context=USER_CTX,
    stream_mode="values",
):
    if chunk.event == "values":
        final = chunk.data

# Check for interrupt
state = await client.threads.get_state(thread_id)
interrupts = [
    it.get("value")
    for t in (state.get("tasks") or [])
    for it in (t.get("interrupts") or [])
]

if interrupts:
    interrupt_value = interrupts[0]
    # Read interrupt_value["question"] and interrupt_value["items"][i]["description"]
    # as user-visible text. Decide reply.
    user_reply = "כן אישור"  # or whatever the scenario calls for
    final = None
    async for chunk in client.runs.stream(
        thread_id, "fitpal",
        command={"resume": user_reply},
        context=USER_CTX,
        stream_mode="values",
    ):
        if chunk.event == "values":
            final = chunk.data
else:
    # Final AI message is the last type=="ai" entry in final["messages"]
    msgs = final.get("messages", [])
    bot_reply = next((m for m in reversed(msgs) if m.get("type") == "ai"), None)
```
