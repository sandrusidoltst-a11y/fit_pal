# Commit Log: 2026-03-01 19:49:40
**Tag:** test
**Message:** test: refactor unit tests and add graph-api E2E tests based on test-engineering skill

## Summary of Changes
- **Unit Test Refactoring**: Updated all 10 unit test files to fully comply with the newly defined patterns in the `test-engineering` skill. Tests now enforce a strict AAA (Arrange/Act/Assert) pattern, isolated mocking structures, and clear docstring documentation.
- **Graph-API Testing Suite**: Created the robust `tests/graph_api/` testing tier using `langgraph-sdk` to execute the full state graph end-to-end against the local LangGraph dev server. 
- **Pytest-Asyncio Fixes**: Fixed event loop issues cascading across test failures by making the `lg_client` fixture function-scoped and adding TCP-based health checks to skip tests if the server isn't running.
- **Dependency Update**: Added `langgraph-sdk` to `pyproject.toml` dependencies.

## Key Insights Discovered
Running the new `graph-api` suit exposed an underlying sync vs async blocking issue. LangGraph's dev server rightfully flags `BlockingError` stemming from `food_lookup.py` tools hitting a synchronous SQLite `get_db_session()` connection while operating inside an asynchronous event loop. 

## Next Steps
- Implement an explicit refactor in `src/tools/food_lookup.py` to change `search_food` and `calculate_food_macros` to be natively asynchronous.
- Re-run the `tests/graph_api/` suite fully to confirm all path testing succeeds and no further structural LLM inconsistencies or DB blocking issues exist.
