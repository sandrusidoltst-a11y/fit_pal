---
name: sync-context
description: Synchronize CLAUDE.md and project skills with the actual project state. Use when the user says "sync context", "update the docs", or after a significant refactor, new skill added, or structural change.
---

# Context Synchronization Workflow

Keep `CLAUDE.md`, `PRD.md`, and `.claude/skills/` accurate and up-to-date with the actual project state, including new skills, structural changes, MCP updates, and patterns learned from recent work.

## 1. Scan Current Documentation

1.  Read `CLAUDE.md` — note the current project structure, architecture patterns, MCP servers, and reference table.
2.  List all skills in `.claude/skills/` and note what each covers.
3.  Read `PRD.md` to understand the intended scope and any recent spec changes.

## 2. Analyze Actual Project State

1.  **Review Conversation History**: Scan recent conversation for:
    - New skills or tools added.
    - Changes to directory structure or file locations.
    - Bug fixes that introduced new rules or patterns (e.g., new architectural constraint).
    - MCP servers added or removed.
    - Explicit user instructions to remember something.
    - New features implemented, nodes added, schemas changed, or flows modified.

2.  **Check Project Structure**:
    ```bash
    tree -L 3 -I '__pycache__|.git|.venv|node_modules'
    ```
    Verify the actual file structure matches the Project Structure section in `CLAUDE.md`.

3.  **Check Skills**:
    - List `.claude/skills/` — are all skills represented in the `CLAUDE.md` reference table?
    - Are any skills outdated or referencing old paths?

4.  **Check PRD Against Implementation** (MANDATORY):
    - Read `PRD.md` fully — note all listed features, milestones, and their statuses.
    - Cross-reference with the actual codebase: read the graph definition (`src/agents/nutritionist.py`), nodes in `src/agents/nodes/`, schemas in `src/schemas/`, and tools in `src/tools/`.
    - Identify features that are **implemented but not reflected in PRD** (missing or still marked as planned/TODO).
    - Identify features **listed in PRD that no longer match** the actual implementation (e.g., renamed nodes, changed flows, removed features).
    - Check milestone statuses — are completed features still marked as "in progress" or "planned"?

## 3. Identify Gaps

Compare **Documented State** (Step 1) with **Actual State** (Step 2). Look for:

- Project structure changes not reflected in `CLAUDE.md`.
- New skills in `.claude/skills/` missing from the reference table.
- MCP servers added/removed not reflected in the MCP Servers section.
- New architectural patterns or rules discovered during recent work.
- Outdated paths, filenames, or commands.
- Validation commands that no longer match the test structure.
- **PRD drift**: Features implemented but PRD not updated, milestone statuses stale, or PRD describing flows that no longer match the code.

## 4. Update Documentation (Only if Needed)

1.  **If GAP FOUND**:
    - **Update `CLAUDE.md`**: Fix structure, add missing reference table rows, update MCP section, add new rules or patterns.
        > **Constraint**: Do NOT add implementation plans (`docs/plans/*.md`) to the reference table. Plans are transient execution artifacts. Only add skills (`.claude/skills/`) or major documentation (`PRD.md`).
    - **Update `PRD.md`**: Mark completed features/milestones as done, add newly implemented features not yet in PRD, correct any flow descriptions that no longer match the code. PRD is a living document — it must reflect reality.
    - **Update Skill Files**: If a skill in `.claude/skills/` references an outdated path or pattern, fix it.

2.  **If NO GAPS**:
    - Do NOT modify any files.

3.  **Notify**: Summarize what was updated, or confirm "Documentation is in sync — no changes needed."
