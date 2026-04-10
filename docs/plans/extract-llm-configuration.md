# Feature: Extract LLM Configuration

The following plan is designed to refactor the hardcoded LLM instantiations across the LangGraph nodes into a centralized, environment-aware configuration pattern.

## Feature Description
Currently, LLM models (e.g., `ChatOpenAI(model="gpt-4o",...`) are hardcoded directly within individual node files (`input_node.py`, `selection_node.py`, `response_node.py`). This feature implements the **Configuration Dictionary Pattern** in `src/config.py`. It establishes global fallback defaults populated by `.env` variables and provides a `get_llm_for_node(node_name)` factory function. This allows for node-specific LLM parameters (like temperature) to be adjusted centrally without modifying the core logic files. It also utilizes LangChain's `init_chat_model` to effortlessly swap between providers (e.g., OpenAI vs Anthropic).

## User Story
As a developer
I want to manage LLM providers, model names, and node-specific parameters (like temperature) from a single configuration file
So that I can easily switch between environments or models without digging into the node logic.

## Problem Statement
Hardcoded `ChatOpenAI` imports and instantiations create tight coupling, prevent easy provider swapping (OpenAI vs Anthropic), and make tweaking temperatures across different nodes cumbersome. 

## Solution Statement
Implement a configuration dict (`NODE_CONFIGS`) in `src/config.py` that maps each node's name to its specific LLM settings (temperature, provider, model_name). Create a `get_llm_for_node(node_name)` factory relying on Langchain's `init_chat_model` that falls back to global `.env` settings if a node-specific config is omitted. Update all nodes to replace `ChatOpenAI` imports with this central factory function.

## Feature Metadata

**Feature Type**: Refactor
**Estimated Complexity**: Low
**Primary Systems Affected**: `config.py` and all files in `src/agents/nodes/`
**Dependencies**: `langchain-core` (for `init_chat_model`), `python-dotenv`

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `src/config.py` - Why: Needs to be expanded to include `GLOBAL_PROVIDER`, `GLOBAL_MODEL`, the `NODE_CONFIGS` dictionary, and the `get_llm_for_node` factory function.
- `src/agents/nodes/input_node.py` - Why: Hardcodes `ChatOpenAI(model="gpt-4o", temperature=0)`. Needs to use factory.
- `src/agents/nodes/selection_node.py` - Why: Hardcodes `ChatOpenAI(model="gpt-4o", temperature=0)`. Needs to use factory.
- `src/agents/nodes/response_node.py` - Why: Hardcodes `ChatOpenAI(model="gpt-4o", temperature=0.7)`. Needs to use factory.

### New Files to Create
*(None required, this is a refactor of existing files).*

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!
- [LangChain init_chat_model Docs](https://python.langchain.com/docs/how_to/chat_models_universal_init/)
  - Why: This is the core LangChain function we will use to make the code provider-agnostic.

### Patterns to Follow

**Configuration Dictionary Pattern**:
Store node-specific settings alongside fallbacks:
```python
GLOBAL_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
GLOBAL_MODEL = os.getenv("LLM_MODEL_NAME", "gpt-4o")

NODE_CONFIGS = {
    "response_node": {"temperature": 0.7},
    "default": {"temperature": 0.0}
}
```

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation
Update `src/config.py` to establish the global rules, the configuration dictionary, and the builder function.

### Phase 2: Core Implementation
Refactor all existing node implementations to consume the new factory function instead of directly importing `langchain_openai.ChatOpenAI`. 

### Phase 3: Testing & Validation
Verify that unit tests using mocked LLMs or integration tests still pass perfectly with the refactored dynamic loading.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### 1. UPDATE `src/config.py`
- **IMPLEMENT**: Add `GLOBAL_PROVIDER` and `GLOBAL_MODEL` reading from `os.getenv`.
- **IMPLEMENT**: Create `NODE_CONFIGS` dict defining `"input_node"`, `"selection_node"`, and `"response_node"` configurations. Set temperature to `0.0` for input/selection, and `0.7` for response.
- **IMPLEMENT**: Create `def get_llm_for_node(node_name: str)` that extracts the config for the node, falls back to globals for missing keys, and returns `init_chat_model(...)`.
- **IMPORTS**: Needs `from langchain.chat_models import init_chat_model`
- **VALIDATE**: `uv run python -c "from src.config import get_llm_for_node; llm = get_llm_for_node('input_node'); print(llm)"`

### 2. UPDATE `src/agents/nodes/input_node.py`
- **REMOVE**: `from langchain_openai import ChatOpenAI`
- **IMPORTS**: `from src.config import get_llm_for_node`
- **UPDATE**: Replace instance instantiation inside `input_parser_node` with `llm = get_llm_for_node("input_node")`. Note: Do not instantiate at the module level to ensure fresh instances are used safely if needed.
- **VALIDATE**: `uv run pytest tests/unit/test_input_parser.py`

### 3. UPDATE `src/agents/nodes/selection_node.py`
- **REMOVE**: `from langchain_openai import ChatOpenAI`
- **IMPORTS**: `from src.config import get_llm_for_node`
- **UPDATE**: Replace instance instantiation inside `agent_selection_node` with `llm = get_llm_for_node("selection_node")`. 
- **VALIDATE**: `uv run pytest tests/unit/test_agent_selection.py`

### 4. UPDATE `src/agents/nodes/response_node.py`
- **REMOVE**: `from langchain_openai import ChatOpenAI`
- **IMPORTS**: `from src.config import get_llm_for_node`
- **UPDATE**: Replace instance instantiation inside `response_node` with `llm = get_llm_for_node("response_node")`.
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py`

### 5. VALIDATE System Integrity
- **VALIDATE**: Run the full test suite to ensure the new dynamic initializations don't break graph flow, mock setups, or typing limits.
- **VALIDATE**: `uv run pytest tests/`

---

## TESTING STRATEGY

### Unit Tests
The major tests exist in `tests/unit/`. Since the LLM instantiation happens *inside* the node functions, `pytest` fixtures that patch `ChatOpenAI` directly might fail if they were specifically patching `src.agents.nodes.input_node.ChatOpenAI`. 
- **Gotcha**: If unit tests fail due to mock issues, update the `patch` paths in the tests to patch `src.config.init_chat_model` or `src.agents.nodes.[name].get_llm_for_node`.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style
`uv run ruff check src/ tests/`

### Level 2: Unit Tests
`uv run pytest tests/unit/`

### Level 3: Full Test Suite
`uv run pytest tests/`

---

## ACCEPTANCE CRITERIA
- [ ] `src/config.py` acts as the single source of truth for LLM instantiation.
- [ ] No nodes directly import `ChatOpenAI` or similar provider-specific models.
- [ ] The `NODE_CONFIGS` dictionary correctly implements the Configuration Object pattern.
- [ ] All unit and integration tests pass cleanly.
- [ ] No functional changes observed in agent outputs.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] Full test suite passes (unit + integration)
- [ ] No linting or type checking errors

---

## NOTES
- LangChain's `init_chat_model` automatically routes API keys if environment variables like `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` exist, streamlining our `.env` needs.
