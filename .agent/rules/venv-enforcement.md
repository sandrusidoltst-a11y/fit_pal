---
trigger: always_on
---

Package Management Standards

Core Mandate: Use uv

All Python package management operations MUST use uv instead of standard pip or poetry commands. This ensures speed, deterministic builds, and unified project management.

Usage Guidelines

1. Installation

Wrong: pip install fastapi

Right: uv add fastapi

2. Dev Dependencies

Wrong: pip install pytest --dev

Right: uv add --dev pytest

3. Running Scripts

Wrong: python main.py

Right: uv run main.py

4. Syncing Environment

Action: When pulling changes or setting up a fresh repo.

Command: uv sync

Why?

Speed: uv is significantly faster at resolving dependencies.

Lockfile: Automatically manages uv.lock for reproducible builds.

Virtual Env: Automatically handles virtual environment creation and activation.