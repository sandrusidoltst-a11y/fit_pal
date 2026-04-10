# Feature: Message Object Typing and Multiple Schemas Refactor

## Feature Description

This feature refactors the LangGraph state definitions to utilize the "Multiple Schemas" pattern (Input, Output, and Internal state) alongside strict typing for LangChain message objects (`HumanMessage`, `AIMessage`, `AnyMessage`). This change ensures the graph's public API contract in LangSmith Studio strictly expects user messages, while enforcing that `input_node.py` and `response_node.py` explicitly construct the appropriate role-based message objects prior to state insertion.

## User Story

As a developer
I want the LangSmith Studio to treat my agent as a chat interface and my internal state to properly delineate between Human and AI messages
So that my LLM always has the correct conversational context and I can debug the agent seamlessly.

## Problem Statement

Currently, the FitPal agent uses a single `AgentState` for all operations, which forces LangSmith Studio to render all internal variables as required form inputs instead of a chat box. Furthermore, the role of specific message types (`HumanMessage` vs `AIMessage` vs `AnyMessage`) within the nodes (`input_node.py`, `response_node.py`) must be strictly clarified and enforced so that the LLM understands who is speaking in the conversation history.

## Solution Statement

1. **State:** Implement LangGraph's Multiple Schemas pattern in `state.py`. We will introduce an `InputState` containing only the `messages` field typed as `List[AnyMessage]`.
2. **Nodes:** Update and ensure that `input_node.py` correctly processes incoming `HumanMessage`s, and `response_node.py` explicitly returns `AIMessage`s.
3. **Graph Initialization:** Update `StateGraph` compilation in `nutritionist.py` to map these explicit schemas: `StateGraph(state_schema=AgentState, input=InputState, output=OutputState)`.

## Feature Metadata

**Feature Type**: Refactor
**Estimated Complexity**: Low/Medium
**Primary Systems Affected**: State definitions (`src/agents/state.py`), Graph compilation (`src/agents/nutritionist.py`), Node implementations (`src/agents/nodes/input_node.py`, `src/agents/nodes/response_node.py`)
**Dependencies**: LangGraph, langchain_core

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `src/agents/state.py` (lines 72-98) - Why: Contains the current monolithic `AgentState` definition. We need to append new state schemas here and type them with `AnyMessage`.
- `src/agents/nutritionist.py` (lines 15-20) - Why: Where `StateGraph(AgentState)` is initialized. We need to update this to accept the new input/output parameters.
- `src/agents/nodes/input_node.py` - Why: Processes the user's input. Needs verification that it expects a `HumanMessage` from the `messages` array.
- `src/agents/nodes/response_node.py` - Why: The final node that replies to the user. It explicitly returns the `result` from the LLM, but we must confirm/ensure it passes back a properly typed `AIMessage` to the state.

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [LangGraph Conceptual Guide: State & Multiple Schemas](https://langchain-ai.github.io/langgraph/concepts/low_level/#multiple-schemas)
  - Specific section: Multiple Schemas pattern
  - Why: Understands how LangGraph magically merges input dicts into the internal state object without requiring code changes to the nodes.

### Patterns to Follow

**Message Object Typing (AnyMessage vs HumanMessage/AIMessage):**
While the internal node files access or create specific `HumanMessage` or `AIMessage` objects so the LLM knows the identity of the speaker, the shared State container must hold a mixture.
- **State (`state.py`)**: `List[AnyMessage]` -> "I accept a list of any type of messages."
- **Input (`main.py` / Studio)**: `HumanMessage("I ate chicken")` -> "The human said this."
- **Output Node (`response_node.py`)**: `AIMessage("I logged it")` -> "The assistant replied with this."

LangGraph's `add_messages` reducer perfectly stitches specific `AIMessage` and `HumanMessage` objects together inside the broad `List[AnyMessage]` container.

**Strong Typing for InputState:**
When defining the new `InputState`, explicitly type the messages list as `List[AnyMessage]` rather than just `List` to enforce strict type checking and assist Studio UI rendering:
```python
from langchain_core.messages import AnyMessage

class InputState(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]
```

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation (State Definitions)

**Tasks:**
- Import `AnyMessage` from `langchain_core.messages` in `state.py`.
- Create `InputState` TypedDict class.
- Create `OutputState` TypedDict class.
- Update `AgentState` to use `List[AnyMessage]`.

### Phase 2: Core Implementation (Nodes & Graph Initialization)

**Tasks:**
- **`nutritionist.py`**: Update imports to include the new schemas and modify `StateGraph` instantiation to pass `input` and `output` schemas.
- **`input_node.py`**: Ensure the node correctly pulls the latest `messages[-1]` (which is a `HumanMessage` injected through the `InputState`) to pass to the structured extraction LLM. *(Note: This logic is already present, but must be verified against the new `AnyMessage` typing).*
- **`response_node.py`**: Ensure the LLM invocation result returned to the state is strictly an `AIMessage` object so the reducer appends it correctly. *(Note: `llm.invoke()` already returns an `AIMessage`, but verify typing and imports).*

### Phase 3: Testing & Validation

**Tasks:**
- Execute the pytest suite.
- Run `uv run ruff check src` to ensure `AnyMessage` typing doesn't crash existing nodes.

---

## STEP-BY-STEP TASKS

### UPDATE `src/agents/state.py`

- **IMPORTS**: Add `from langchain_core.messages import AnyMessage`
- **IMPLEMENT**: Add `InputState(TypedDict)` with property `messages: Annotated[List[AnyMessage], add_messages]`
- **IMPLEMENT**: Add `OutputState(TypedDict)` with property `messages: Annotated[List[AnyMessage], add_messages]`
- **IMPLEMENT**: Update the existing `AgentState` messages property to use `Annotated[List[AnyMessage], add_messages]`
- **VALIDATE**: `uv run ruff check src/agents/state.py`

### UPDATE `src/agents/nutritionist.py`

- **IMPORTS**: Update import from `src.agents.state` to include `InputState` and `OutputState` alongside `AgentState`.
- **IMPLEMENT**: Change `workflow = StateGraph(AgentState)` to `workflow = StateGraph(state_schema=AgentState, input=InputState, output=OutputState)`
- **VALIDATE**: `uv run ruff check src/agents/nutritionist.py`

### REFACTOR `src/agents/nodes/input_node.py`

- **VALIDATE**: Ensure that `last_message = state["messages"][-1]` is logically sound assuming it is receiving a `HumanMessage` via the new `InputState`. Provide type hints if needed to satisfy Ruff/Mypy.

### REFACTOR `src/agents/nodes/response_node.py`

- **VALIDATE**: Ensure `result = llm.invoke(full_messages)` correctly captures the `AIMessage` returned by ChatOpenAI, and that returning `{"messages": [result]}` correctly returns an `AIMessage` back to the global state container (as defined by the pattern).

---

## TESTING STRATEGY

### Unit Tests

Because nodes inherently receive the merged internal `AgentState` regardless of the `InputState`, logic tests should pass. Pay special attention to test setups that mock `AgentState` directly; ensure they pass properly formatted `HumanMessage`s if they aren't already.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

`uv run ruff check src`

### Level 2: Unit Tests

`uv run pytest tests/unit/`

### Level 3: Manual Validation

1. `uv run langgraph dev`
2. Open LangSmith Studio web UI
3. Confirm that the configuration pane on the right side ONLY asks for "Messages" and presents a chat UI, instead of asking for `current_date`, `last_action`, etc.
4. Input a message and verify traces show a `HumanMessage` going in and an `AIMessage` coming out.

---

## ACCEPTANCE CRITERIA

- [ ] `InputState` and `OutputState` explicitly defined in `state.py`.
- [ ] `StateGraph` correctly utilizes the Multiple Schemas pattern.
- [ ] State lists are strictly typed with `AnyMessage`.
- [ ] Nodes correctly depend on and produce standard LangChain message objects (`HumanMessage`, `AIMessage`).
- [ ] LangSmith Studio correctly interprets the `InputState` schema and offers a standard conversational interface.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Full test suite passes (unit + integration)
- [ ] No linting or type checking errors
- [ ] Manual testing confirms feature works

---

## NOTES

This structural refactor defines the strict API boundaries of the graph. We enforce that `state.py` handles the abstract `AnyMessage` container, while the external world injects `HumanMessage`s and `response_node.py` yields `AIMessage`s. This guarantees LLMs downstream correctly infer conversational roles.
