# Feature: Implement Intelligent Response Node

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

The `response_node` is the final step in the FitPal LangGraph flow. Currently, it exists as an inline placeholder in `src/agents/nutritionist.py` returning hardcoded strings based on the `last_action`. This feature replaces that placeholder with a dynamic, LLM-powered response generator. It will intelligently read the final `AgentState`, extract relevant context (e.g., successful/failed logging attempts, queried daily stats), format it cleanly as JSON, and use `ChatOpenAI` to generate a natural, conversational reply while maintaining full chat history.

## User Story

As a disciplined tracker
I want the agent to reply to me with natural, informative messages about what it just did (logged my food, fetched my stats, or asked for clarification)
So that I feel like I'm texting a helpful assistant rather than interacting with a rigid database script.

## Problem Statement

The MVP currently uses placeholder string responses (e.g., "Food logged successfully!") in the response node. This breaks the conversational experience, fails to provide granular feedback for multi-item logs (e.g., telling the user *which* food failed to log), and prevents the agent from actually answering questions about a user's historical data when they trigger a `QUERY_DAILY_STATS` action.

## Solution Statement

Extract the `response_node` into its own file (`src/agents/nodes/response_node.py`) following the existing node patterns. The new node will:
1. Extract the conversation history (`state["messages"]`).
2. Read the `last_action` to determine intent.
3. Selectively extract relevant data from the state (`processing_results` for logging actions, `daily_log_report` for stats queries).
4. Serialize this tailored state data into a clean JSON string to prevent LLM hallucination and context-window bloating.
5. Prepend a dynamically constructed `SystemMessage` to the conversation history, injecting the JSON context and a system prompt (loaded from a new markdown file).
6. Invoke the LLM to generate an `AIMessage` and return it to update the state.

## Feature Metadata

**Feature Type**: Enhancement
**Estimated Complexity**: Medium
**Primary Systems Affected**: `src/agents/nodes/response_node.py`, `src/agents/nutritionist.py`, `prompts/response_generator.md`
**Dependencies**: `langchain-openai`, `json` stdlib

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `src/agents/nutritionist.py` (lines 20-37) - Why: Contains the current inline placeholder `response_node` that needs to be removed and replaced with an import.
- `src/agents/nodes/selection_node.py` (lines 53-75) - Why: Contains the established pattern for loading prompt markdown files, injecting context into `SystemMessage`/`HumanMessage`, and invoking the LLM. We will mirror this pattern.
- `src/agents/state.py` (lines 87-96) - Why: Contains the `AgentState` TypedDict definition. You must understand fields like `messages`, `processing_results`, `daily_log_report`, and `last_action`.

### New Files to Create

- `src/agents/nodes/response_node.py` - Core logic for generating the LLM response.
- `prompts/response_generator.md` - System prompt template guiding the agent's persona and how it should interpret the injected JSON context.
- `tests/unit/test_response_node.py` - Unit tests mocking the LLM and validating context injection.

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [LangChain Message History & State](.agent/skills/langchain-architecture/SKILL.md)
  - Specific section: Memory Management and Architecture Patterns
  - Why: Demonstrates how to correctly pass `SystemMessage`, `HumanMessage`, and `AIMessage` arrays to the `llm.invoke()` method to maintain conversation memory.

### Patterns to Follow

**LLM Instantiation & Invocation:**
```python
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage

def get_response_llm():
    return ChatOpenAI(model="gpt-4o", temperature=0.7) # Slightly higher temp for conversational responses

# ... inside node:
llm = get_response_llm()
system_message = SystemMessage(content=f"{system_prompt}\nContext:\n{json_context}")
# Prepend system message to history
full_messages = [system_message] + state.get("messages", [])
result = llm.invoke(full_messages)
return {"messages": [result]}
```

**Prompt File Loading:**
Mirror the pattern from `selection_node.py` using `os.path.join(os.getcwd(), "prompts", "response_generator.md")` with a fallback string if the file isn't found.

**Selective Context Injection:**
Do not pass the entire state. Filter based on `last_action`. Use `json.dumps(..., indent=2)` as discussed to provide clean payloads.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation
- Create the prompt template file to define the agent's persona and its instructions for interpreting the injected context JSON.

### Phase 2: Core Implementation
- Create `response_node.py` taking `AgentState` as input.
- Implement the selective JSON generation logic based on `last_action` (`LOGGED`/`FAILED` vs `QUERY_DAILY_STATS`).
- Merge the prompt, the JSON context, and the conversation history.
- Invoke `ChatOpenAI` and return the `AIMessage`.

### Phase 3: Integration
- Remove the placeholder `response_node` from `src/agents/nutritionist.py`.
- Import the new `response_node` from `src/agents/nodes/response_node.py`.
- Ensure graph compilation remains successful.

### Phase 4: Testing & Validation
- Create unit tests verifying that the node properly handles empty contexts, logging contexts (`processing_results`), and query contexts (`daily_log_report`), and accurately appends an AIMessage to the state.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### 1. CREATE prompts/response_generator.md
- **IMPLEMENT**: Create a markdown file defining the system prompt. Instruct the LLM that it is "FitPal", a helpful fitness coach. Tell it to look at the injected JSON context to answer the latest user query naturally. Warn it to NEVER hallucinate nutritional numbers, but to rely strictly on the provided JSON. Make the tone friendly but concise.

### 2. CREATE src/agents/nodes/response_node.py
- **IMPLEMENT**: Create the node module. Define `get_response_llm()` (using `gpt-4o` with `temperature=0.7`). Define `response_node(state: AgentState) -> dict`. 
- **IMPLEMENT**: Add logic to check `last_action`. If `LOGGED` or `FAILED`, format `state.get("processing_results", [])` to JSON. If `QUERY_DAILY_STATS`, format `state.get("daily_log_report", [])` to JSON. Include `current_date` in the context.
- **PATTERN**: Mirror prompt file loading from `src/agents/nodes/selection_node.py`.
- **IMPORTS**: `os`, `json`, `ChatOpenAI` from `langchain_openai`, `SystemMessage` from `langchain_core.messages`, `AgentState` from `src.agents.state`.
- **GOTCHA**: Ensure you prepend the `SystemMessage` to the front of `state.get("messages", [])` when invoking the LLM to preserve history without losing the system instructions.
- **VALIDATE**: `uv run ruff check src/agents/nodes/response_node.py`

### 3. REFACTOR src/agents/nutritionist.py
- **IMPLEMENT**: Delete the inline `response_node` function (approx lines 20-37).
- **IMPLEMENT**: Import `response_node` from `src.agents.nodes.response_node` at the top of the file.
- **VALIDATE**: `uv run ruff check src/agents/nutritionist.py`

### 4. CREATE tests/unit/test_response_node.py
- **IMPLEMENT**: Write unit tests using `unittest.mock.patch` to mock `ChatOpenAI.invoke`. 
- **IMPLEMENT**: Test three scenarios: (1) Logging context (`processing_results` present), (2) Stats Context (`daily_log_report` present), (3) General Chat/Ambiguous (`NO_MATCH` action). Check that the node returns a dict with `{"messages": [mock_ai_message]}`.
- **IMPORTS**: `pytest`, `patch`, `AIMessage`, `HumanMessage`, `AgentState`, `response_node`.
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v`

---

## TESTING STRATEGY

### Unit Tests
We will use Pytest along with `unittest.mock.patch` to intercept the LLM call inside `response_node.py`. The goal is to ensure the payload (specifically the `messages` array passed to `invoke()`) is constructed correctly and that the output dictionary adheres to the expected format for updating LangGraph state.

### Edge Cases
- State has no `messages` history
- `last_action` is unrecognized or empty
- Prompt file is accidentally deleted (fallback prompt triggers)
- Empty lists for `processing_results` or `daily_log_report`

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style
`uv run ruff check src/`
`uv run ruff format src/ --check`

### Level 2: Unit Tests
`uv run pytest tests/unit/test_response_node.py -v`

### Level 3: Integration Tests
*(Assuming a broader test suite exists, run all tests to ensure the graph compiles)*
`uv run pytest tests/ -v`

---

## ACCEPTANCE CRITERIA

- [ ] `response_node` is successfully extracted to a standalone file.
- [ ] LLM actively parses `processing_results` to confirm logged items and ask about failed items seamlessly.
- [ ] LLM actively parses `daily_log_report` to answer questions about historical stats.
- [ ] All unit tests Mock the LLM correctly and verify the exact context arrays constructed.
- [ ] Graph compilation in `main.py` succeeds without error.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit + integration)
- [ ] No linting or type checking errors
- [ ] Manual testing confirms feature works
- [ ] Acceptance criteria all met
- [ ] Code reviewed for quality and maintainability
