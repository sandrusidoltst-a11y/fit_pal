---
description: Comprehensive project validation and code review
---

# Validation Workflow

Ensure project quality through automated checks and systematic review.

## 1. Automated Validation

**Goal**: Run standard checks to catch errors early.

1.  **Linting**:
    - Backend: `uv run ruff check .`
    - Frontend: `npm run lint`
2.  **Type Checking**:
    - Backend: `uv run mypy backend/`
    - Frontend: `npm run typecheck`
3.  **Unit Tests**:
    - Backend: `uv run pytest -v`
    - Frontend: `npm test`
4.  **Test Coverage** (Optional):
    - `uv run pytest --cov=backend`
5.  **Build**:
    - Frontend: `npm run build`

## 2. Code Review

**Goal**: Review recent changes for logic, security, and quality.

1.  **Context**: Check `.agent\rules\main-rule.md, `README.md`.
2.  **Analyze Diffs**:
    - `git diff HEAD`
    - `git ls-files --others --exclude-standard`
3.  **Check For**:
    - **Logic Errors**: Off-by-one, race conditions.
    - **Security**: Injections, exposed secrets.
    - **Performance**: N+1 queries, leaks.
    - **Quality**: DRY, naming, typing.
4.  **Verify**: Run specific tests for any issues found.

## 3. System Review (Post-Implementation)

**Goal**: Analyze process adherence and identify improvements.

1.  **Compare**: Planned Approach vs. Actual Implementation.
2.  **Identify Divergences**:
    - **Good**: Justified improvements.
    - **Bad**: Shortcuts, misunderstandings.
3.  **Root Cause**: Why did bad divergences happen?
4.  **Improve**:
    - Update `main-rule.md` with new patterns.
    - Update workflow files with clarifications.