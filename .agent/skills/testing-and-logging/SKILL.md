---
name: testing-and-logging
description: Hub for structured logging and comprehensive testing strategies. Use when setting up, refactoring, or extending logging and testing infrastructure.
---

# Testing & Logging Hub

This skill provides a modular reference for structured logging and testing strategies.

## Quick Links

- **[logging.md](references/logging.md)**: Structlog configuration, FastAPI integration, and context binding.
- **[unit-testing.md](references/unit-testing.md)**: Pytest guides, mocking, and pure function testing.
- **[integration-testing.md](references/integration-testing.md)**: API endpoints, database rollbacks, and FastAPI TestClient.
- **[e2e-testing.md](references/e2e-testing.md)**: Playwright setup and critical user journey scenarios.

## Execution Logic

> [!IMPORTANT]
> **Context Optimization Strategy**
> - If the user asks for **"full test coverage"** or a broad overhaul, you MUST consult **all** reference files.
> - If the user focuses on a **specific layer** (e.g., "Unit Tests", "Logging config"), work **exclusively** with the relevant reference file to minimize context usage.

## Testing Overview

### The Testing Pyramid

| Layer | Percentage | Speed | Scope |
|-------|------------|-------|-------|
| Unit | 70% | ms | Single function/class |
| Integration | 20% | seconds | Multiple components |
| E2E | 10% | minutes | Full system |

### Directory Structure

```
tests/
├── conftest.py                 # Shared fixtures
├── pytest.ini                  # Pytest configuration
├── unit/                       # See unit-testing.md
├── integration/                # See integration-testing.md
└── e2e/                        # See e2e-testing.md
```
