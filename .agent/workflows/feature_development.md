---
description: Comprehensive feature development workflow (Prime -> Plan -> Execute)
---

# Feature Development Workflow

This workflow guides you through the full lifecycle of implementing a new feature, from initial context gathering to final execution.

## 1. Prime: Load Context

**Goal**: Build a comprehensive understanding of the codebase.

1.  **Analyze Project Structure**:
    - Run `git ls-files` to see tracked files.
    - Run `tree` (or equivalent) to visualize directory structure.
2.  **Read Core Documentation**:
    - Read `.agent\rules\main-rule.md`, `README.md`, and any architecture docs.
3.  **Identify Key Files**:
    - Read main entry points, config files, and core models.
4.  **Understand Current State**:
    - Check `git status` and recent `git log`.

## 2. Plan: Create Implementation Plan

**Goal**: Transform the feature request into a detailed, executable plan.

1.  **Feature Understanding**:
    - Extract the core problem and user value.
    - Create/Refine the User Story.
2.  **Codebase Intelligence**:
    - Analyze project structure, patterns, dependencies, and integration points.
    - **CRITICAL**: Read relevant codebase files and documentation *before* planning.
3.  **External Research**:
    - Research libraries, tools, and best practices if new technologies are involved.
4.  **Strategic Thinking**:
    - Consider edge cases, failure modes, testing strategies, and security.
5.  **Generate Plan**:
    - Create a plan file in `.agent/plans/` (e.g., `feature-name.md`).
    - The plan MUST include:
        - Feature description & User Story.
        - **Context References**: Specific files and lines to read.
        - **Step-by-Step Tasks**: Atomic, ordered tasks with specific actions (CREATE, UPDATE, etc.).
        - **API Contract**: If creating endpoints, explicitly link strictly to `backend/schemas.py`.
        - **Validation Commands**: Non-interactive commands to verify *each* step.
        - **Accceptance Criteria**.

## 3. Execute: Implement from Plan

**Goal**: implement the feature by strictly following the plan.

1.  **Read the Plan**:
    - Understand the full scope and dependencies.
2.  **Execute Tasks**:
    - Follow the "Step-by-Step Tasks" in order.
    - **Verify as you go**: Check syntax and imports after every change.
3.  **Implement Tests**:
    - Write unit and integration tests as specified in the plan.
4.  **Run Validation**:
    - Run ALL validation commands specified in the plan.
    - Fix any issues immediately.
5.  **Final Verification**:
    - Ensure all acceptance criteria are met.
    - Confirm the project is ready for a commit.
