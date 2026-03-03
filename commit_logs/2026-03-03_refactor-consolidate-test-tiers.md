# Consolidate Test Tiers: 3 → 2

**Date**: 2026-03-03
**Commit**: `138aa30`
**Tag**: `refactor`

## Changes

- **Removed `tests/integration/` tier entirely** — consolidated into unit and graph_api
- **Moved** `test_graph_compilation.py` from `integration/` to `graph_api/` with improved AAA docstrings
- **Deleted** `test_food_db.py` (real DB tests) and `test_llm_prompts.py` (real LLM tests) — prompt quality is better evaluated via LangSmith traces, not flaky pytest assertions
- **Updated docs**: CLAUDE.md, PRD.md, test-engineering SKILL.md, validation SKILL.md, fitpal-test-strategy.md, graph-api-testing.md
- **Fixed** duplicate `graph_api/` line in PRD.md project structure
- **Updated** `testing_graph.excalidraw` with graph-api test annotations

## Rationale

The integration tier blurred boundaries — some tests used real LLM (non-deterministic), some used real DB (slow). Graph compilation fits naturally in `graph_api/`. Prompt evaluation belongs in LangSmith Studio, not pytest.

## Next Steps

- Add more graph-api E2E flow tests covering all routing paths
- Consider LangSmith evaluator for prompt quality regression
