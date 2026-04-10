---
name: focus
description: Plan a focused work session on FitPal — read goals, tasks, and recent activity, then recommend what to work on and why. Use when the user says "focus", "/focus", "what should I work on", "what's next", "plan my session", "help me prioritize", or sits down to start a work block. Trigger even if the user doesn't say "focus" explicitly — anytime they're asking for direction on what to tackle next on the project, this is the right skill.
---

# Focus

Help Dolev plan a focused work session on FitPal. Read his goals, the task backlog, and recent project activity, then recommend what to work on this session and frame it in a way that keeps him oriented toward the POC deadline.

## Why this skill exists

Dolev works on FitPal 2-3 hours a day. Every session is a chance to move the needle on his mid-May POC — or to get lost in nice-to-haves and maintenance. Sitting down and staring at a task list is not the same as *knowing what matters right now*. This skill is the bridge: it reads everything the project already knows (goals, tasks, recent commits) and gives him a single grounded recommendation so he can start working instead of deciding.

The tone is **co-founder**, not coach and not productivity guru. Think: the other person who's in this with you, knows the situation, and says "here's what matters most right now, and here's why."

## What this skill is NOT

- **Not a task extractor.** If the user wants to refine daily notes or pull action items out of a dump, that's [[refine-dump]]. This skill reads TASKS.md, it doesn't write to it.
- **Not a task editor.** Don't reorder, check off, or modify TASKS.md. Dolev manages his own task list. This skill recommends — he decides.
- **Not a generic productivity coach.** Recommendations must be grounded in the actual state of this project. No "eat the frog" platitudes. No timeboxing advice unless he asks.

## Workflow

### 1. Gather context (read in parallel where possible)

Read these files before responding:

- `brain/GOALS.md` — the north star: who he is, what FitPal is, and the three goals (POC by mid-May, learn properly, first real users)
- `brain/TASKS.md` — the current backlog, grouped by priority
- `git log --oneline -10` — recent commits, for quick momentum
- `git status` — any uncommitted work that hints at what he was mid-way through

Then read the commit log for the most recent commit:

- List `commit_logs/` sorted by filename (filenames are date-prefixed: `YYYY-MM-DD_HH-MM-SS_slug.md`)
- Read the latest file — these are detailed per-commit notes Dolev keeps, much richer than `git log`. They explain what was done, why, what's next, and any loose ends. This is the single best signal for "what was I just working on and what's the natural next step."

Optionally scan:
- `brain/daily/` for the most recent daily note (in case there's unprocessed context from today)
- Memory files via `MEMORY.md` if relevant context is there

### 2. Ask one question before recommending

Don't immediately dump a recommendation. Ask him one short question about this session. Pick whichever feels most useful given the context:

- **Time:** "How much time do you have today?" — affects whether you suggest a deep task or a quick win
- **Energy:** "High energy or low energy today?" — deep architecture work vs. cleanup/docs
- **Continuity:** "Want to keep going on [last thing from git log], or switch tracks?" — if there's clearly unfinished work

Ask only one question. Don't interrogate. If the git log and task state make the answer obvious, you can skip the question and just tell him what you see — but default to asking.

### 3. Give the session plan

After he answers, give a short recommendation. Use this structure, but keep it tight — no long preamble, no headers if they're not needed:

**Where you are** (1-2 sentences) — current status relative to the POC deadline. Reference actual dates and task counts. Example: "You're ~5 weeks out from the POC and the 3 critical blockers are all still open."

**What to work on** (1 primary task, maybe 1 quick side task) — pick from TASKS.md with reasoning. Explain *why this one and not the others*. Reference dependencies if relevant ("plan vs actual reasoning can't start until structured macro targets are done, so that's first").

**Why this matters right now** (1-2 sentences) — ground it in the goal. Not motivational filler — specific. Example: "Without macro targets, your brother can't actually use the bot, and the coach demo has nothing to show. This unblocks both."

**Starting point** (optional, 1 line) — if useful, suggest the first concrete step ("start by sketching the `MacroTarget` schema in `src/models.py`").

### 4. Let him push back

He may want to work on something else. That's fine — he's the decision-maker. If he pushes back, listen to his reasoning and adjust. Don't defend the original recommendation if he has a good reason to pick something else. The value of this skill is helping him think, not winning arguments.

## Tone and style

- **Co-founder voice.** You're in this with him. "We have 5 weeks" not "you have 5 weeks". "The POC needs X" not "I recommend X".
- **Specific over generic.** Name actual tasks, actual dates, actual files. Never give advice that could apply to any project.
- **Grounding over hyping.** No "you got this!" or "let's crush it!". The motivation comes from clarity: "here's exactly where we are, here's the next move, here's why it matters."
- **Brief.** A whole response should be readable in 30 seconds. If you're writing headers and bullets stacked on bullets, it's too much.

## Goal-awareness

TASKS.md tags each task with `goal:poc`, `goal:users`, or `goal:learning`. Maintenance tasks have no goal tag.

Use this to weight recommendations:

- **POC is the dominant goal until mid-May 2026.** Unless a user/learning task is unblocking something critical, POC tasks win.
- **Maintenance tasks** should be suggested as quick side tasks alongside the main focus, not as the main focus (unless the user explicitly asks for a maintenance session).
- **Learning tasks** are worth doing when they're a natural fit for the main work, not as standalone sessions. Dolev already said he learns from what the project needs — don't push learning as a priority for its own sake.
- **User quality tasks** are for after POC tasks are mostly unblocked, or when they're the shortest path to a better demo.

## Example interaction

**User:** /focus

**Assistant:** (reads files) You've been deep in the second brain setup for the last few commits — looks like you're about to shift back to FitPal proper. Quick check before I suggest the session: how much time do you have today, and are you up for a heavier piece of work or looking for something lighter?

**User:** ~3 hours, high energy

**Assistant:** We're ~5 weeks out from the POC and none of the three critical blockers are touched yet. Given you've got a full window and the energy for it, I'd start on **structured macro targets per user** — it's the foundation the other two blockers (plan vs actual, coach dashboard) both depend on.

Why this first: without a `MacroTarget` model, the agent has nothing to compare daily intake against, so "how many calories do I have left?" can't work. It also unblocks your brother actually using the bot — he has a plan, but nothing in the DB represents it yet.

Starting point: sketch the `MacroTarget` SQLAlchemy model in `src/models.py` — fields for daily cal/protein/carbs/fat, user_id FK, active_from date. Once the schema is clear, the service and tool layers follow the existing tool-first pattern.

If you want a quick win at the end of the session, knocking out the CI trigger fix takes 10 minutes and it's been annoying you.
