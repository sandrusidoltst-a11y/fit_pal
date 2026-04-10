---
name: refine-dump
description: Refine raw brain dump daily notes into structured Obsidian notes with wikilinks, tags, and task extraction. Use when the user says "refine dump", "refine today", "process my notes", "refine daily note", or wants to turn raw bullet-point brain dumps into organized learning/planning/idea notes. Also trigger when the user mentions brain dumps, daily notes, or Obsidian note processing, even if they don't say "refine" explicitly.
---

# Refine Dump

Turn raw daily brain dump notes into structured, organized Obsidian notes with wikilinks, tags, and task extraction.

## Why this skill exists

The user captures thoughts fast in daily notes — mixed bullets about learnings, planning, ideas, debugging, all in one file. They shouldn't have to think about organization while capturing. This skill does the organizing after the fact: splitting chunks into separate typed notes, fixing typos, translating to English if needed, linking to related code/docs, and copying action items to a central task file.

The key principle: **organize, don't elaborate**. The skill restructures what the user wrote — it never adds context, explanations, or tasks the user didn't write.

## Invocation

The skill accepts these forms:
- `/refine-dump` — refines today's daily note (`brain/daily/YYYY-MM-DD.md`)
- `/refine-dump 2026-04-08` — refines a specific date's note
- `/refine-dump brain/daily/2026-04-10.md` — refines a specific file path

## System layout

```
brain/
├── daily/           # Raw daily notes (gitignored) — NEVER modify these
├── learnings/       # Refined learning notes
├── planning/        # Refined planning notes
├── ideas/           # Refined idea notes
└── TASKS.md         # Central task list with wikilinks to source notes
```

The repo root is the Obsidian vault. All wikilinks should work relative to the vault root.

## Step-by-step workflow

### 1. Resolve the input file

Determine which daily note to process based on the invocation arguments:
- No argument: use today's date to build the path `brain/daily/YYYY-MM-DD.md`
- Date argument: build path from that date
- File path argument: use as-is

Read the file. If it doesn't exist, tell the user and stop.

### 2. Collect existing tags

Before processing, scan for tags already used in `brain/` notes so you can reuse them for consistency. Grep for `tags:` lines in frontmatter across `brain/**/*.md` and build a set of known tags. When tagging new notes, prefer existing tags over creating new ones (e.g., if `telegram-bot` already exists, don't create `telegram` or `bot` as separate tags).

### 3. Detect chunks and classify

Read through the dump and split it into separate chunks. Each chunk is a distinct topic or thought thread.

**Boundary detection:**
- Explicit `---` separators the user placed — these are hard boundaries, always split here
- Topic shifts — if the user switches from talking about aiogram to talking about auth, that's a new chunk even without a separator. Use judgment, but err on the side of fewer splits (don't over-fragment)

**Classification — ask when unsure:**
- **learning** — the user understood something new (a concept, a framework, how code works)
- **planning** — what to work on, what's next, debugging investigation plans
- **idea** — a feature idea, a "we should do X", something for the future

If a chunk doesn't clearly fit one type, ask the user: "This chunk about [brief description] — is this a learning, planning, or idea note?" Don't guess on ambiguous ones.

### 4. For each chunk, scan the repo for related files

Use Grep and Glob to find code files, commit logs, plans, patterns, and docs related to the chunk's content. Look in:
- `src/` — code files mentioned or related to the topic
- `commit_logs/` — relevant commit history
- `docs/plans/` — implementation plans
- `docs/patterns/` — architecture patterns
- `docs/` — documentation, RCA docs
- `bot/` — bot-related code

These become `[[wikilinks]]` in the refined note.

### 5. Create refined notes

For each chunk, create a refined note in the appropriate subfolder.

**Filename:** If the user provided a name in the dump (e.g., a clear title or heading), use it as a slug. Otherwise, generate a descriptive slug from the content (e.g., `aiogram-gateway-architecture.md`, `confirmation-flow-questions.md`).

**Frontmatter format:**
```yaml
---
date: YYYY-MM-DD
type: learning | planning | idea
tags: [tag1, tag2, tag3]
source: "URL here"  # only if the user included a link in the dump
---
```

**Content rules:**
- Fix typos and grammar
- Translate to English if the dump is in Hebrew or another language
- Structure into logical sections with headers
- Add `[[wikilinks]]` to related repo files found in step 4
- Questions stay as questions — do NOT convert them to action items or checkboxes
- Action items the user explicitly wrote become `- [ ]` checkboxes
- Do NOT add explanations, context, or elaboration the user didn't write
- Do NOT invent tasks or action items — only extract what the user explicitly stated as something to do

**Note structure by type:**

Learning notes:
```markdown
# [Title]

## [Logical sections based on content]
[Structured content with wikilinks]

## Open Questions
[Any questions from the dump]

## Links
[Wikilinks to related code/docs]
```

Planning notes:
```markdown
# [Title]

[Structured content]

## Action Items
- [ ] [Only items the user explicitly wrote as things to do]

## Open Questions
[Questions stay here, not as tasks]

## Related Code & Docs
[Wikilinks]
```

Idea notes:
```markdown
# [Title]

[The idea, structured]

## Related Code & Docs
[Wikilinks if relevant]
```

### 6. Update TASKS.md

After creating all refined notes, check if any of them contain explicit action items (checkboxes). If so, append those tasks to `brain/TASKS.md` with a wikilink back to the source note.

**Format in TASKS.md:**
```markdown
- [ ] Task description — [[brain/learnings/source-note|source]]
```

If `TASKS.md` doesn't exist yet, create it with a `# Tasks` header.

Only add tasks that the user explicitly wrote as things to do. Questions, observations, and learnings are NOT tasks. When in doubt, leave it out.

### 7. Report what was created

After writing all files, show the user a summary:
- List of refined notes created (with paths)
- Tasks added to TASKS.md (if any)
- Any chunks you skipped or questions you have

## Important constraints

- **Never modify the daily note** — it's the raw capture log and stays untouched
- **Never add content the user didn't write** — organize and restructure only
- **Never invent tasks** — only extract explicitly stated action items
- **Always output in English** — translate Hebrew or other languages
- **Reuse existing tags** — check what tags already exist before creating new ones
- **Questions are not tasks** — they stay as questions in the note, never go to TASKS.md
