---
name: adr
description: Create a new Architecture Decision Record (ADR) in docs/adr/. Use when the user says "/adr", "create adr", "write an adr", "record this decision", or just finished an architectural conversation and wants to capture the outcome. Drafts the decision from recent conversation context, walks the user through each section for confirmation, then writes the detail file and appends to DECISIONS.md. Rejects invocation when there is no prior architectural discussion to draw from.
---

# ADR

Capture an architectural decision as a permanent record in `docs/adr/`. One file per decision. Immutable after acceptance. Indexed in `docs/adr/DECISIONS.md`.

## Why this skill exists

Architectural decisions in FitPal get made in conversation — during debugging, planning, dogfooding, or live refactors — and then evaporate. Six months later, future-Dolev sees a design choice and has no record of *why* it was made, *what* was considered, or *when* it should be reopened. That gap turns stage-appropriate decisions into tech-debt horror stories.

ADRs fix that. They are not documentation of how the system works — they are records of choices, preserved with their reasoning.

This skill exists because writing ADRs is low-ceremony but non-zero effort. It should feel like a 5-minute wrap-up after a decision lands, not a separate project. The skill handles the file plumbing (numbering, index entry, template) so Dolev focuses on the content.

## What this skill is NOT

- **Not a decision-maker.** The decision must already be made. This skill captures it; it does not help reach it. If Dolev is still weighing options, route to `plan-feature` or just keep the conversation going.
- **Not a rewriter of old ADRs.** Once an ADR is accepted, its detail file is immutable. Changing a past decision means writing a *new* ADR that supersedes the old one.
- **Not a silent-draft generator.** Do not draft all six sections and dump them. Walk section by section — the point is that Dolev confirms each before it lands.
- **Not a cold-start template.** If there is no prior architectural discussion in the current conversation, reject with "Start with a conversation about the decision, then invoke /adr to capture it." Do not fill in blanks from nothing.

## Preconditions — reject when absent

Before doing anything else, validate that the current conversation contains an architectural discussion worth recording. Signals:

- Multi-turn discussion of a design choice, trade-off, or architectural concern
- Mentions of specific alternatives considered or rejected
- Discussion of system components, auth, data flow, deployment, or similar
- The user's invocation references "this decision", "this conversation", "what we just discussed", or equivalent

If none of these apply (e.g., the invocation comes after a coding task, a test run, a bug fix, or an unrelated chat), reject:

> I don't see an architectural discussion in our recent conversation to draw from. Start with a conversation about the decision — context, alternatives, trade-offs — then invoke /adr to capture it. ADRs written from nothing become generic and lose their value.

Do not proceed to draft. Do not ask if the user wants to write one from scratch.

## Workflow

### 1. Gather context

In parallel, read:
- `docs/adr/DECISIONS.md` — to see existing entries and the template shape
- `ls docs/adr/` — to find the highest existing ADR number
- Scan the current conversation for the decision, alternatives, trade-offs, and revisit conditions

Compute the next ADR number: highest existing `NNNN-` prefix + 1, zero-padded to 4 digits (`0001`, `0002`, …, `0042`).

### 2. Propose the title and slug first

Before anything else, show the user:
- **Proposed title** — short, specific, phrased as the chosen decision (not the question). Example: *"App-layer user authorization via user_id scoping"*, not *"How should we handle auth?"*
- **Proposed slug** — kebab-case, used in the filename. Example: `0007-app-layer-user-authorization`.
- **Proposed area** — one or two keywords: auth, data, deploy, testing, ux, cost, infra, llm, security, …

Ask the user to confirm or adjust all three in one message. Do not start drafting sections until the title is locked.

### 3. Walk through each section

Once title/slug/area are confirmed, walk the six sections one or two at a time — not all at once. For each section:

1. **Draft from conversation.** Summarize what you inferred from the discussion. Be specific, quote constraints or statements the user made, cite file paths where relevant.
2. **Ask for confirmation or edits.** Short, direct: *"Does this capture the context, or do you want to adjust?"*
3. **Never invent.** If the conversation didn't cover a section, say so and ask. Do not fill consequences or alternatives from general knowledge.
4. **Move on when confirmed.** Don't re-polish.

Sections, in order:

1. **Context** — the constraints and situation that forced the decision. What made this a real choice, not an obvious one?
2. **Decision** — the choice, stated directly. One or two sentences, no hedging.
3. **Alternatives considered** — each serious alternative with *why it was rejected*. Minimum two; usually three. Do not invent alternatives Dolev didn't discuss.
4. **Consequences** — three subsections: *What this makes easier*, *What this makes harder*, *What we are committing to*. This is where honesty about the trade-off lives.
5. **Revisit trigger** — the condition(s) that should reopen this decision. Must come from the user, not the assistant. If Dolev hasn't thought about this, ask directly: *"What would make us reopen this? Scale? A specific event? A date?"* The answer is the most valuable field in the ADR.
6. **Related** — links to code files, plans, other ADRs, task entries, RCA docs. Draft from what was mentioned in conversation; ask for additions.

### 4. Write the detail file

Use the detail template from `docs/adr/DECISIONS.md`. The file should:

- Live at `docs/adr/NNNN-slug.md`
- Start with the title, status, area, deciders
- Have all six sections fully populated with the confirmed content
- Not include any commentary, meta-notes, or "TODO" markers — if a section isn't ready, don't write the ADR yet

**Status format**: `Accepted YYYY-MM-DD`. Use today's date. Only use `Proposed` if Dolev explicitly says the decision is tentative.

### 5. Append the index entry

Open `docs/adr/DECISIONS.md`. Find the `## Decisions` heading. Append a new `### ADR-NNNN: Title` subsection at the bottom (append, do not insert — chronological order matches numeric order).

The entry uses the index-row template:

```markdown
### ADR-NNNN: Title

- **Status**: Accepted (YYYY-MM-DD) · revisit <short trigger>
- **Area**: <area>
- **One-liner**: <single sentence summarizing the decision>
- **Trade-off**: <what we accepted in exchange>
- **Detail**: [full record](NNNN-slug.md)
- **Conversation**: [[brain/conversations_beckups/YYYY-MM-DD_slug]] *(to be backed up)*
- **Related**: <comma-separated links, short>
```

The `Conversation` field uses a `(to be backed up)` marker when the conversation hasn't been exported yet. Dolev manages conversation backups separately; do not create the backup file.

### 6. Report and hand off

Show the user:
- Path to the new detail file
- The new DECISIONS.md entry (inline, so they don't have to open it)
- Any loose ends: conversation backup needed, related files not yet linked, consequences that felt thin

Do NOT auto-commit. Do NOT run validation. The user decides when to commit.

## File targets

- `docs/adr/DECISIONS.md` — the index. Append-only for new entries; existing entries may have their `Status` line updated when superseded (not by this skill — by the skill invocation that creates the superseding ADR).
- `docs/adr/NNNN-slug.md` — the detail file. Immutable after this skill writes it.

## Style rules for the ADR text

- **One-liner must be one sentence.** If it spans two, the decision isn't crisp enough — push back.
- **Alternatives must have a *why rejected* line each.** No bare alternatives.
- **Revisit trigger must be concrete.** "When we scale" is not concrete. "First real coach onboards with their own trainees" is concrete.
- **Related links use inline paths, not wikilinks** (unless pointing into `brain/`, where wikilinks work).
- **Do not use emoji.** Do not use exclamation points. The tone is sober and lasting.

## Interaction with sync-context

This skill does not update `CLAUDE.md`. If the Reference Table in `CLAUDE.md` needs to point at `docs/adr/DECISIONS.md`, that is `sync-context`'s job. Mention it in the hand-off only if no reference currently exists.

## Edge cases

- **User invokes /adr then realizes the decision isn't firm yet** — stop. Suggest reverting to discussion or using `plan-feature`. Do not write a speculative ADR.
- **User invokes /adr for a decision already captured** — check the index. If the decision already exists, ask whether this is a *supersede* (write ADR-NNNN that references the old one, then update the old index row's status to `Superseded by ADR-NNNN`) or a duplicate (cancel).
- **The conversation covers multiple decisions** — ask which one to capture. Do not batch multiple ADRs in one invocation.
- **No `docs/adr/DECISIONS.md` exists** — report and stop. Do not bootstrap the folder from this skill; the folder is set up by hand once.
