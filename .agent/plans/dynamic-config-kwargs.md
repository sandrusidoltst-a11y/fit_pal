# Feature: Allow Configurable LLM Parameters via kwargs

The following plan is designed to address architectural reviews on Pull Request #7. It refactors `src/config.py` to allow any valid LangChain parameter to be passed to nodes, and documents the newly extracted `.env` variables in `README.md`.

## Feature Description
Currently, `get_llm_for_node` explicitly looks for only `"temperature"`, `"provider"`, and `"model"` keys within the `NODE_CONFIGS` dictionary. This prevents developers from defining other valid parameters like `max_tokens`, `stop`, or `frequency_penalty`. This plan updates the factory function to consume a merged dictionary and unpack it using Python's `**kwargs` syntax directly into `init_chat_model`. It also updates the `README.md` to document the global variables `LLM_PROVIDER` and `LLM_MODEL_NAME`.

## User Story
As a developer
I want to configure any valid LLM parameter via the `NODE_CONFIGS` dictionary
So that I am not artificially limited by the factory function's hardcoded extraction logic.

## Problem Statement
The central configuration factory drops all keys from `NODE_CONFIGS` except three specific hardcoded values, making it impossible to configure advanced LLM capabilities natively. The newly added `.env` parameters were also missing from the project's setup documentation.

## Solution Statement
Refactor `src/config.py` to dynamically construct a parameter dictionary with fallback `model` and `provider` defaults, apply the specific node overrides using `.update()`, and pass the whole dictionary via `**kwargs` into `init_chat_model`. Finally, append documentation to `README.md` explaining the `NODE_CONFIGS` structure and new `.env` settings.

## Feature Metadata

**Feature Type**: Enhancement / Refactor
**Estimated Complexity**: Low
**Primary Systems Affected**: `config.py`, `README.md`
**Dependencies**: `langchain-core`

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `src/config.py` (lines 24-37) - Why: Contains the manual dictionary extraction logic that needs replaced with `**kwargs` unpacking.
- `README.md` (lines 48-60) - Why: Contains the Environment Variable templates where documentation for `LLM_PROVIDER` must be added.

### New Files to Create

*(None required).*

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [LangChain init_chat_model kwargs parameters](https://python.langchain.com/docs/how_to/chat_models_universal_init/)
  - Why: Assures developers that `init_chat_model` safely receives `**kwargs` and maps them to the respective provider's class initialization (e.g. `max_tokens` dropping into `ChatOpenAI`).

### Patterns to Follow

**Dictionary Unpacking Pattern (`**kwargs`)**:
Instead of this explicit code:
```python
temperature = config.get("temperature", 0.0)
return init_chat_model(model=model, temperature=temperature)
```
Do this:
```python
# Create base defaults
params = {
    "model_provider": GLOBAL_PROVIDER, 
    "model": GLOBAL_MODEL, 
    "temperature": 0.0
}
# Overlay specific node config (this allows `max_tokens` or anything else)
params.update(NODE_CONFIGS.get(node_name, NODE_CONFIGS.get("default", {})))

# Handle the specific API key renaming rule for init_chat_model
if "provider" in params:
    params["model_provider"] = params.pop("provider")

return init_chat_model(**params)
```

---

## IMPLEMENTATION PLAN

### Phase 1: README Documentation
Update `README.md` to explicitly mention `LLM_PROVIDER`, `LLM_MODEL_NAME`, and how they fallback in `src/config.py`.

### Phase 2: Configuration Refactoring
Update `get_llm_for_node` in `src/config.py` to smartly merge the node-specific dictionary over a base dictionary of fallback parameters, then return the `init_chat_model(**merged_dict)`.

### Phase 3: Validation
Execute unit tests to ensure the unpacked arguments construct the mock models precisely as before.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### 1. UPDATE `README.md`
- **IMPLEMENT**: In the `Environment Variables` section, add `LLM_PROVIDER=openai` and `LLM_MODEL_NAME=gpt-4o` to the snippet block. Add a quick explanation that these drive the defaults for the `NODE_CONFIGS` engine.
- **VALIDATE**: N/A for markdown.

### 2. UPDATE `src/config.py`
- **IMPLEMENT**: Rewrite `get_llm_for_node` to use `dict.update()` semantics and then unpack `**params` into `init_chat_model`. Make sure to safely map the `provider` key to `init_chat_model`'s required `model_provider` parameter.
- **GOTCHA**: `NODE_CONFIGS` might contain the key `"provider"`. But `init_chat_model` specifically requires the argument `model_provider`. Be sure to `.pop("provider")` and re-insert it as `model_provider` if it exists in the merged dictionary, or just handle it cleanly!
- **VALIDATE**: `uv run python -c "from src.config import get_llm_for_node; print(get_llm_for_node('input_node'))"`

### 3. VALIDATE Project Integrity
- **VALIDATE**: `uv run ruff check src/ tests/`
- **VALIDATE**: `uv run pytest tests/`

---

## TESTING STRATEGY

### Unit Tests
The refactor simply expands *how* we pass arguments; it does not change *what* arguments are passed right now (`temperature=0.0`). The existing Mock setups in `test_response_node.py` and others will successfully intercept the `**kwargs` instantiation without requiring changes.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style
`uv run ruff check src/ tests/`

### Level 2: Full Test Suite
`uv run pytest tests/`

---

## ACCEPTANCE CRITERIA
- [ ] `src/config.py`'s `get_llm_for_node` returns `init_chat_model(**params)`.
- [ ] `README.md` explicitly lists `LLM_PROVIDER` and `LLM_MODEL_NAME`.
- [ ] All unit and integration tests pass cleanly.

---

## COMPLETION CHECKLIST
- [ ] All tasks completed in order
- [ ] Full test suite passes
- [ ] No linting or type checking errors

---

## NOTES
- By using `**kwargs`, we future-proof our LLM setup so that developers can easily attach JSON schema enforcers, stop limits, and frequency penalties directly to specific nodes via the configuration dictionary.
