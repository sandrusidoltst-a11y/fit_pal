# Commit Log: 2026-02-22 - Refactor Config for Advanced LLM Parameters

## Changes Implemented
- **Dynamic Config Iteration (`src/config.py`)**: Replaced the explicit `.get()` pulling of exactly three keys with Python dictionary `.update()` and `**kwargs` unpacking. The `get_llm_for_node` factory now safely extracts the specific node dictionary, merges it over a base configuration containing global default fallbacks, and handles renaming `"provider"` to `"model_provider"` for `init_chat_model` compatibility. 
- **Configuration Hierarchy Details**: Added comprehensive docstrings to `config.py` clarifying exactly how the Node-Specific overrides Global and Hardcoded defaults, complete with a link to LangChain's exhaustive kwargs documentation.
- **`README.md` Additions**: Documented `LLM_PROVIDER` and `LLM_MODEL_NAME` directly within the setup section to clarify environment defaults.

## Next Steps
- Implement **Asynchronous Database Migration** using `AsyncSession` to safely structure data logging loops moving forward without locking the SQLite file.
- Look into handling **Relative Time & Past Logging** interpretation ("yesterday", "last night").
