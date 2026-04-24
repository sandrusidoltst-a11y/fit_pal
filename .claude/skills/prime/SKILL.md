---
name: prime
description: Load and understand project context. Use at the start of a new session, when switching tasks, or when the user says "prime yourself", "load context", or "get up to speed".
---

# Prime: Load Project Context

## Objective

Build comprehensive understanding of the codebase by analyzing structure, documentation, and key files.

## Process

### 1. Analyze Project Structure

List all tracked files:
```bash
git ls-files
```

Show directory structure:
```bash
tree -L 3 -I 'node_modules|__pycache__|.git|dist|build'
```

### 2. Read Core Documentation

- Read `CLAUDE.md` at the project root — this is the primary context file
- Read `README.md` at the project root and major directories
- Read any architecture documentation

#### Context-aware PRD loading (FitPal-specific)

Check the current branch name (`git rev-parse --abbrev-ref HEAD`) and recent commits/modified files for signals about the active workstream. Then load the PRD(s) relevant to that work:

- **Bot / agent / LangGraph work** (default) — read `PRD.md`.
- **Dashboard work** — read `DASHBOARD_PRD.md` **in addition to** `PRD.md` when any of these signals are present:
  - Current branch name contains `dashboard`, `dash`, `coach-ui`, `frontend`, or `feat/dashboard-phase-N`
  - Recent commits or modified files touch `dashboard/` or `src/dashboard/`
  - The user's task or question mentions: coach dashboard, frontend, trainee list screen, trainee detail screen, macros-vs-plan view, plan upload, food catalog editor, coach auth, body stats panel, progress photos, or any coach-facing UI

If signals are ambiguous, err on the side of reading both PRDs.

**Important about `DASHBOARD_PRD.md`:** most decisions in that document are Claude-proposed defaults flagged for re-discussion during implementation planning. Treat the PRD as a structural scaffold, not committed decisions. Each phase kicks off with a `/plan-feature` session that decides the real *how*.

### 3. Identify Key Files

Based on the structure, identify and read:
- Main entry points (`main.py`, `index.ts`, `app.py`, etc.)
- Core configuration files (`pyproject.toml`, `package.json`, `tsconfig.json`)
- Key model/schema definitions
- Important service or controller files

### 4. Understand Current State

Check recent activity:
```bash
git log -10 --oneline
```

Check current branch and status:
```bash
git status
```

## Output Report

Provide a concise summary covering:

### Project Overview
- Purpose and type of application
- Primary technologies and frameworks
- Current version/state

### Architecture
- Overall structure and organization
- Key architectural patterns identified
- Important directories and their purposes

### Tech Stack
- Languages and versions
- Frameworks and major libraries
- Build tools and package managers
- Testing frameworks

### Core Principles
- Code style and conventions observed
- Documentation standards
- Testing approach

### Current State
- Active branch
- Recent changes or development focus
- Any immediate observations or concerns
- **Active workstream signal**: bot work, dashboard work, or mixed — based on branch and recent commits

**Make this summary easy to scan - use bullet points and clear headers.**
