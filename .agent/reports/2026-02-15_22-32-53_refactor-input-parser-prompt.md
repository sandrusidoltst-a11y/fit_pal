# Refactor: Restructure Input Parser Prompt for Intent-First Logic

## Summary of Changes
- **Updated Prompt (`prompts/input_parser.md`):**
    - Restructured to prioritize **Intent Identification** before data extraction.
    - Explicitly defined 4 action paths: `LOG_FOOD`, `QUERY_DAILY_STATS`, `QUERY_FOOD_INFO`, `CHITCHAT`.
    - Added specific instructions to return empty lists for non-logging actions.
- **Updated Tests (`tests/unit/test_input_parser.py`):**
    - Added `test_query_daily_stats`: Verifies "How much protein left?" -> `QUERY_DAILY_STATS`.
    - Added `test_query_food_info`: Verifies "Calories in apple?" -> `QUERY_FOOD_INFO`.
    - Validated that existing logging flows still work correctly.

## Purpose
To fix the logic flow in the Input Parser node. Previously, the prompt was biased towards extracting food from every query, leading to potential hallucinations when users asked for stats or general info. The new structure ensures the agent "thinks" about the user's goal before trying to parse food items.

## Verification
- `uv run pytest tests/unit/test_input_parser.py` passed (7/7 tests).
