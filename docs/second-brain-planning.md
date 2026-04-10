# Second Brain Planning — Obsidian for FitPal

## Goal

Create an Obsidian-based second brain for the FitPal project. Replace paper brain dumps with a low-friction digital system that links thoughts to code, chats, commit logs, and plans.

---

## What We Established

### How Obsidian Works (mental model)

- **Vault** = just a folder on your computer. No database, no lock-in. Any folder of markdown files works.
- **Notes** = plain `.md` files inside the vault. One file = one note.
- **Wikilinks** = `[[note name]]` syntax. Click to navigate. If the target note doesn't exist yet, clicking creates it. **Link first, create later.**
- **Backlinks** = open any note and Obsidian shows every other note that links TO it. This is the killer feature — organization becomes emergent.
- **Tags** = `#fitpal/auth`, `#learning`, etc. Click a tag to see all notes with it. Tags are collectors that don't require a hub note.
- **Frontmatter** = YAML block at the top of a note (date, type, tags, etc.). Queryable with Dataview plugin.

### Key insight: you don't need hub notes upfront

- You can write `[[Auth]]` even though `Auth.md` doesn't exist. It renders as a grey placeholder link.
- Weeks later, if you click it and create `Auth.md`, its backlinks panel **immediately shows every note that ever referenced `[[Auth]]`** — retroactively.
- Tags (`#fitpal/auth`) and backlinks on shared files (`src/security/auth.py`) act as implicit hubs without any dedicated note.
- Structure is emergent, not planned.

### Linking to everything from a brain dump

From a single dump note, you can link to:
- **Claude chat**: regular markdown URL link `[description](https://claude.ai/chat/abc123)`
- **Code files**: `[[src/security/auth.py]]` (needs vault inside repo + "Detect all file extensions" setting)
- **Commit logs**: `[[commit_logs/2026-03-15-shared-secret-middleware]]` (already markdown, already in repo)
- **Plans/patterns**: `[[docs/patterns/tool-first]]` or any other repo markdown
- **Concept notes**: `[[JWT]]`, `[[Defense in depth]]` — may not exist yet, that's fine

### The capture/process split

The core workflow idea:

1. **Capture** (human, fast, paper-like): raw bullet points, no formatting, no links, no decisions. Friction must be near zero.
2. **Process** (skill-assisted, later): a Claude Code skill reads the raw dump, scans the repo for related code/commits/plans, and produces a structured note with frontmatter, wikilinks, grouped sections, and concept note suggestions.

**What you type** (raw):
```
auth fitpal
- why 2 auth systems?? confusing
- dev = jwt langgraph thing
- prod = shared secret X-Internal-Token
- diff threat models
- bot only client so shared secret is enough
- user_id from body not jwt
- RLS still on - defense in depth
- leaked token?? rotate how
chat: https://claude.ai/chat/abc123
```

**What the skill produces** (refined):
A structured note with frontmatter, sections (what I learned / open questions / next actions), wikilinks to `src/security/auth.py`, `commit_logs/...`, `[[JWT]]`, `[[Row Level Security]]`, etc.

You do the thinking. The skill does the boring organization.

---

## Two Types of Brain Dumps Identified

1. **Planning dumps** — "what do I work on next, why, what's blocking me." Attached to a date. Used when deciding next moves on the project.
2. **Learning dumps** — what you understood from a new framework / PR review / concept study. Often paired with a Claude Desktop/web chat you want to link back to and potentially resume.

Both need the same capture/process workflow but may need different refinement templates (planning → extract action items; learning → extract concepts and open questions).

---

## Open Design Questions (not yet decided)

### Vault location
- [ ] Inside the repo (e.g., `brain/` folder) — enables wikilinks to code files, commit logs, patterns. Git = sync/backup. Tradeoff: brain dumps in git history.
- [ ] Outside the repo (standalone vault) — more private, but can't wikilink to repo files directly.
- [ ] Repo IS the vault (point Obsidian at repo root) — all existing markdown becomes notes automatically. Most powerful, most noisy.

### Capture surface
- [ ] **Daily note** (one file per day, everything goes there) — lowest friction, most paper-like
- [ ] **Inbox folder** (one file per dump) — more granular
- [ ] **Single rolling scratchpad** — simplest

### Skill behavior
- [ ] Overwrite raw dump with refined version
- [ ] Append refined below raw in the same file
- [ ] Keep raw untouched, write refined to separate folder (recommended)

### Skill invocation
- [ ] Manual (`/refine-dump`) when the dump feels done
- [ ] Autopilot vs. interactive (does it ask questions or just guess?)
- [ ] Should it handle both planning and learning dumps, or separate skills?

### Review cadence
- [ ] Weekly review to harvest planning dumps into decisions/tasks?
- [ ] End-of-session wrap-up habit?

### Frameworks considered
- **PARA** (Projects/Areas/Resources/Archives) — action-oriented
- **Zettelkasten** — atomic concept notes, linked by meaning
- **Daily-note-first / LYT** — low friction capture, refactor into Maps of Content later
- **Current lean**: daily-note-first with skill-assisted refinement

---

## Next Steps

Continue this discussion in local Claude Code. Key decisions to make:
1. Where does the vault live relative to the repo?
2. Daily note vs. inbox folder for capture?
3. Sketch the refine-dump skill behavior
4. Design templates for planning vs. learning dumps
5. Consider Obsidian plugins needed (Daily Notes, Templater, Dataview)
