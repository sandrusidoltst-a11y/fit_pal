---
description: Analyze root cause and implement fixes for bugs (RCA -> Fix)
---

# Bug Fix Workflow

Systematic process for analyzing and fixing bugs, ensuring root causes are addressed and verified.

## 1. Root Cause Analysis (RCA)

**Goal**: Understand why the bug exists before fixing it.

1.  **Fetch Issue Details**:
    - Use `gh issue view [issue-id]` to get context.
2.  **Search Codebase**:
    - Locate relevant code, error messages, and patterns.
3.  **Review History**:
    - Check recent changes with `git log`.
4.  **Investigate**:
    - Determine if it's a logic error, edge case, or integration issue.
5.  **Create RCA Document**:
    - Create `docs/rca/issue-[id].md`.
    - Include: Problem Description, Reproduction Steps, Root Cause Analysis, **Broader Codebase Scan Results**, Proposed Fix, and **Validation Commands**.

## 2. Implement Fix

**Goal**: Apply the fix defined in the RCA.

1.  **Read RCA**:
    - Understand the strategy and files to modify.
2.  **Verify Current State**:
    - Reproduction steps to confirm the bug exists.
3.  **Apply Code Changes**:
    - Modify files as planned.
    - Handle related changes and imports.
4.  **Add Tests**:
    - Create test cases to verify the fix and prevent regression.
    - **Test Cases**: Fix verification, edge cases.

## 3. Validate and Verify

**Goal**: Ensure the fix works and breaks nothing else.

1.  **Run Validation**:
    - Execute commands from RCA (linting, type checking, tests).
    - `python -m pytest [test-file]`
2.  **Manual Verification**:
    - Follow reproduction steps to confirm resolution.
3.  **Finalize**:
    - Update documentation if needed.
    - Commit with message `fix: resolve issue #[id]`.
