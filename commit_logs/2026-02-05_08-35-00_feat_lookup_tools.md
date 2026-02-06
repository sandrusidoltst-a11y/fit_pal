# Commit Log: Implement Food Lookup Logic & Dependencies

**Timestamp**: 2026-02-05 08:35:00
**Tag**: `feat` / `build`

## Summary of Changes
1.  **Feature Implementation (`feat/lookup-calc-logic`)**:
    -   Implemented `src/tools/food_lookup.py` with `search_food` and `calculate_food_macros`.
    -   Added `src/models.py` defining the `FoodItem` SQLAlchemy model.
    -   Added `src/database.py` for DB session handling.
    -   Modified `src/scripts/ingest_db.py` to support explicit IDs.
    -   Added `tests/test_food_lookup.py` and passed all unit tests.

2.  **Dependency Updates**:
    -   Added `sqlalchemy` for database interactions.
    -   Added `langchain-openai` for future agent integration.

## Next Steps
-   Resume integration of tools into `src/agents/nutritionist.py` (currently paused).
-   Verify agent graph with manual testing.
