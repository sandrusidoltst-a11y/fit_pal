---
description: Synchronize documentation (main_rule, PRD, Reference Table) with recent project changes and conversation history.
---

# Context Synchronization Workflow

Use this workflow to ensure `main_rule.md` and referenced documents remain up-to-date with the actual project state, including new skills, structure changes, or bug fixes.

## 1. Scan Documentation
1.  Read `.agent/rules/main_rule.md`.
2.  Identify all files listed in the **Reference Table** (e.g., `PRD.md`, skills).
3.  Read the content of these referenced files to understand the current documented state.

## 2. Analyze Conversation & Project State
1.  **Review History**: Scan the recent conversation history for:
    - New skills or tools added.
    - Changes to directory structure or file locations.
    - Bug fixes that imply new rules or patterns (e.g., "Always use `uv`").
    - Explicit user context additions.
2.  **Check Project Structure**: Run `ls -R` or `tree` (via `list_dir`) to verify if the actual file structure matches `main_rule.md`.

## 3. Identify Gaps
Compare the **Documented State** (Step 1) with the **Actual State** (Step 2). Look for:
- Missing entries in the Reference Table.
- Outdated paths or filenames.
- detailed rules that need updating based on recent "lessons learned".

## 4. Update Documentation (Only if Needed)
1.  **If GAP FOUND**:
    - **Update `main_rule.md`**: Add missing rows, update structure, or add critical rules.
        > **Constraint**: Do NOT add implementation plans (e.g., `plans/*.md`) to the Reference Table. These are transient and serve only the execution phase. Only add Skills, Rules, or major Documentation (PRD).
    - **Update Referenced Files**: If a specific rule file (like `venv-enforcement.md`) needs an update.
2.  **If NO GAPS**:
    - Do NOT modify any files.
3.  **Notify**: Summarize what was updated (or state that "Documentation is in sync").
