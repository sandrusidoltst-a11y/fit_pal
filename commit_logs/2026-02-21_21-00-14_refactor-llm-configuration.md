# Commit Log: 2026-02-21 - Extract LLM Configuration

## Changes Implemented
- **Refactoring LLM Nodes**: Removed hardcoded `ChatOpenAI` models and temperatures inside `input_node.py`, `selection_node.py`, and `response_node.py`.
- **Centralized Configuration**: Implemented a node configuration dictionary pattern in `src/config.py` using `init_chat_model` allowing robust fallback generation, configurable via environment parameters (`LLM_PROVIDER`, `LLM_MODEL_NAME`).
- **Tests Refactored**: Re-pointed `unittest.mock.patch` paths from specific component imports to the global config's output inside `test_response_node.py`, `test_feedback_logic.py`, and `test_feedback_integration.py` to maintain mocked consistency. Fixed a test flake in `test_input_parser.py` relating to checking `CHITCHAT` intent.
- **Workflow & Documentation Sync**: Updated `.agent/workflows/core-piv-loop/execute.md` to clarify efficient, localized testing procedures instead of executing expensive global test frameworks after every minor update. Synchronized `main_rule.md` and `PRD.md` with accomplishments.

## Next Steps
- Implement **Asynchronous Database Migration** using `AsyncSession` to safely structure data logging loops moving forward without locking the SQLite file.
- Look into handling **Relative Time & Past Logging** interpretation ("yesterday", "last night").
