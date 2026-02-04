---
description: Create a new commit for uncommitted changes
---

# Commit Workflow

Streamline the process of adding, tagging, and committing changes.

## 1. Check Status

1.  Run `git status` to see current state.
2.  Run `git diff HEAD` to view changes.
3.  Run `git status --porcelain` for a clean list of uncommitted files.

## 2. Stage Changes

1.  Add untracked and modified files: `git add <files>` or `git add .`

## 3. Commit

1.  **Format**: Use an atomic commit message.
    - **Tag**: Use standard tags like `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.
    - **Message**: Concise description of changes.
2.  **Execute**: `git commit -m "tag: message"`

## 4. Log Progress

1.  **Documentation**: For every commit, create a Markdown document summarizing the changes implemented and outlining the next steps.
2.  **Naming**: Save the file with a timestamped filename including a brief description of the changes: `YYYY-MM-DD_HH-mm-ss_brief-description.md`.
