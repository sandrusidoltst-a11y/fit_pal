# Commit Log: Input Parser Refactor & Verification

## Changes Implemented
- **Schema Refactor**: Split `quantity` (str) into `amount` (float) and `unit` (Literal["g"]) in `InputSchema`.
- **Prompt Logic**: Updated `input_parser.md` to mandate unit normalization to grams and generic naming.
- **Testing Infrastructure**: 
  - Migrated from `verify_input_logic.py` to `tests/unit/test_input_parser.py` (Pytest).
  - Added `tests/conftest.py`.
- **Documentation**: Synced `main_rule.md` and `PRD.md` with new structure and data standards.

## Verification
- Ran `uv run pytest` -> 5/5 tests passed.
- Validated complex inputs ("cup of rice" -> 200g, generic name "rice").

## Next Steps
- Implement logic in `calculate_food_macros` to handle the new `amount` and `unit` inputs cleanly.
