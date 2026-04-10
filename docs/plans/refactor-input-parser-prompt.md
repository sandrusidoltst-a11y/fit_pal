# Feature: Refactor Input Parser Prompt for Intent-First Logic

## Feature Description

The current `input_parser.md` prompt jumps immediately into food extraction rules ("Decompose Meals", "Unit Normalization") without clearly instructing the LLM to first determine the user's *intent*. This causes confusion when the user asks for stats (e.g., "How much protein do I have left?") or engages in chitchat, as the LLM might try to force-extract food items.

This refactor will restructure the system prompt to explicitly prioritize **Intent Classification** before **Data Extraction**.

## User Story

As a user
I want the agent to understand when I am asking for my daily stats vs. logging food
So that it doesn't try to log "protein" as a food item when I ask "How much protein left?".

## Problem Statement

The current prompt structure treats `last_action` as a byproduct of extraction failure. It should be the *primary* decision. The agent needs to know *what* it is doing (Logging vs Querying vs Chitchat) before it tries to do it.

## Solution Statement

Restructure `prompts/input_parser.md` into a 2-step reasoning process:
1.  **Step 1: Classify Intent**: Select one of `[LOG_FOOD, QUERY_DAILY_STATS, QUERY_FOOD_INFO, CHITCHAT]`.
2.  **Step 2: Execute Strategy**:
    -   **LOG_FOOD**: Decompose and Normalize.
    -   **QUERY_DAILY_STATS**: Set action, return empty list.
    -   **CHITCHAT**: Set action, return empty list.

## Feature Metadata

**Feature Type**: Refactor / Enhancement
**Estimated Complexity**: Low
**Primary Systems Affected**: `prompts/input_parser.md`
**Dependencies**: None

---

## CONTEXT REFERENCES

### Relevant Codebase Files

- `prompts/input_parser.md` - Target file to rewrite.
- `src/schemas/input_schema.py` - Defines the `ActionType` enum values we must map to.

### Patterns to Follow

**Chain of Thought Prompting**:
Instruct the LLM to "Reason first" about the intent, then extract.

---

## IMPLEMENTATION PLAN

### Phase 1: Rewrite Prompt

**Goal**: Update the markdown file.

**Tasks**:
- Rewrite `prompts/input_parser.md` to use the "Intent First" structure.
- Explicitly list the valid `ActionType` values (`LOG_FOOD`, `QUERY_DAILY_STATS`, `CHITCHAT`).
- Add examples for `QUERY_DAILY_STATS` (e.g., "Calories left?", "What have I eaten?").

### Phase 2: Validation

**Goal**: Verify the new prompt works with the existing tests.

**Tasks**:
- Run `tests/unit/test_input_parser.py` to ensure no regression in extraction capability.
- Add new test cases for `QUERY_DAILY_STATS` if missing.

---

## STEP-BY-STEP TASKS

### REWRITE `prompts/input_parser.md`

- **IMPLEMENT**: Replace content with new Intent-First instructions.
- **VALIDATE**: `uv run pytest tests/unit/test_input_parser.py`

---

## TESTING STRATEGY

- **Unit Tests**: Existing tests cover `LOG_FOOD` and `CHITCHAT`. We rely on these to ensure the refactor doesn't break the core "logging" feature.

---

## VALIDATION COMMANDS

```bash
uv run pytest tests/unit/test_input_parser.py
```

---

## ACCEPTANCE CRITERIA

- [ ] Prompt explicitly instructs to identify Intent first.
- [ ] `QUERY_DAILY_STATS` is clearly defined as an option.
- [ ] All existing input parser tests pass.
