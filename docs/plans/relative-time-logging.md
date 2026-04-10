# Feature: Relative Time Logging

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Upgrade the extraction logic in the `Input Parser Node` to gracefully handle relative timestamps ("2 hours ago", "yesterday") and convert them into exact datetimes for the SQLite `DailyLog` database. This ensures accurate logging for past meals, increasing overall flexibility and addressing user needs.

## User Story

As a Disciplined Tracker
I want to log food I ate in the past (e.g., "I ate an apple 2 hours ago" or "yesterday")
So that my daily macro tracking remains accurate even if I forget to log the meal immediately.

## Problem Statement

Currently, `FoodIntakeEvent` only extracts a naive `target_date` (just a `date` object). If a user logs a meal they had "2 hours ago", the system currently defaults to the database insertion time, making chronological tracking inaccurate within a single day. 

## Solution Statement

Update the `FoodIntakeEvent` schema to extract an exact `consumed_at` timestamp. To achieve this without complex regular expressions, we will dynamically inject the current server time into the `input_parser.md` prompt, allowing the LLM to do the relative math. The `calculate_log_node` will then insert this specified time into the `DailyLog` table. A fallback mechanism will be put in place where if only a date is mentioned (e.g. "yesterday"), the system will default to 12:00 PM on that date. If nothing is mentioned, it defaults to the exact server completion time.

## Feature Metadata

**Feature Type**: Enhancement
**Estimated Complexity**: Medium
**Primary Systems Affected**: `input_node`, schemas (`input_schema.py`, `state.py`), `calculate_log_node`
**Dependencies**: None (Uses existing `datetime` logic and Langchain structured outputs).

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `src/schemas/input_schema.py` (lines 35-46) - Why: Contains `target_date` and `timestamp` which need to be replaced with a single `consumed_at` `datetime` field.
- `src/agents/state.py` (lines 38) - Why: `current_date: date` needs to be updated to `consumed_at: Optional[datetime]`.
- `prompts/input_parser.md` (lines 4-15) - Why: This is where we instruct the LLM on date/time extraction rules.
- `src/agents/nodes/input_node.py` (lines 28-36) - Why: Here we need to grab `datetime.now()` and format the prompt to include the current system time.
- `src/agents/nodes/calculate_log_node.py` (lines 40-44) - Why: Handles generating the `datetime` sent to SQLite. We must use the `consumed_at` from the state if available.
- `src/agents/nodes/stats_node.py` - Why: Needs to be reviewed to ensure range queries still function if `start_date` and `end_date` are kept separate.
- `tests/unit/test_input_parser.py` - Why: Test pattern example for the `input_node`.
- `tests/unit/test_calculate_log_node.py` - Why: Validates the timestamp sent to the `daily_log_service`.

### New Files to Create
No new files are required for this enhancement.

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!
- Python `datetime` module documentation for handling `timezone.utc`. 
- Pydantic v2 documentation for `Optional[datetime]` fields.

### Patterns to Follow

**Current Time Injection:**
Get a unified current time before invoking LLM:
```python
from datetime import datetime
now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
system_prompt = f"The current system time is: {now_str}\n\n" + system_prompt
```

**TODOs for Phase 2:**
Mark areas that will require timezone updates later with a distinct comment:
`# TODO: Phase 2 - Update default calculations to accommodate user timezones`

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation (Schema Update)
Modify the structural boundaries of the graphs to accept the new `consumed_at` property rather than abstract dates.

**Tasks:**
- Update `FoodIntakeEvent` in `input_schema.py` to use `consumed_at: Optional[datetime]`. Remove `target_date` and `timestamp`.
- Update `AgentState` in `state.py` to track `consumed_at`.

### Phase 2: Core Implementation (Prompt & Parser Logic)
Inject the system time so the LLM has temporal context.

**Tasks:**
- Update `prompts/input_parser.md` to add explicit fallback hierarchy rules for calculating relative times.
- Update `src/agents/nodes/input_node.py` to inject `datetime.now()` into the string before converting to a `SystemMessage`.
- Update `input_node.py` state mapping logic to pass `consumed_at` to the state output. 

### Phase 3: Integration (Database Writing)
Ensure the `calculate_log_node.py` actually uses the LLM-extracted time.

**Tasks:**
- Update `calculate_log_node.py` to check for `consumed_at` in the state. If it exists, use it. If not, default to the immediate `datetime.now(timezone.utc)`.

### Phase 4: Testing & Validation
Validate the logical outputs via mock LLM chains.

**Tasks:**
- Update existing tests in `test_input_parser.py` to mock the system prompt output and verify `consumed_at` parsing.
- Update `test_calculate_log_node.py` to pass an artificial `consumed_at` in the state and ensure it hits the `create_log_entry` mock correctly.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### 1. UPDATE `src/schemas/input_schema.py`
- **IMPLEMENT**: Remove `target_date` and `timestamp` fields from `FoodIntakeEvent`.
- **ADD**: Insert `consumed_at: Optional[datetime] = Field(None, description="The exact date and time the food was consumed...")` including the fallback instructions (use 12:00 PM if only date is provided, leave null if nothing).
- **VALIDATE**: `uv run ruff check src/schemas/input_schema.py`

### 2. UPDATE `src/agents/state.py`
- **IMPLEMENT**: Replace `current_date: date` with `consumed_at: Optional[datetime]` in the `AgentState` TypedDict.
- **VALIDATE**: `uv run ruff check src/agents/state.py`

### 3. UPDATE `prompts/input_parser.md`
- **IMPLEMENT**: Update the `action` logic for `LOG_FOOD`. Instruct the LLM to output `consumed_at` based on the fallback hierarchy (Exact Time provided -> Relative Time parsed from System Time -> Specific Date at 12:00:00 -> Null).
- **VALIDATE**: Check for markdown formatting consistency.

### 4. UPDATE `src/agents/nodes/input_node.py`
- **IMPORTS**: Make sure `datetime` is imported.
- **IMPLEMENT**: At the top of `input_parser_node`, grab `now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")`. Prepend `f"The current system time is: {now_str}\n\n"` to the loaded `system_prompt`.
- **UPDATE**: Inside the return `updates` dictionary, map `result.consumed_at` to the state, and handle `start_date` / `end_date` logic without referencing the removed `current_date`.
- **VALIDATE**: `uv run ruff check src/agents/nodes/input_node.py`

### 5. UPDATE `src/agents/nodes/calculate_log_node.py`
- **IMPLEMENT**: Change lines 36-44. Retrieve `consumed_at` from `state`. If `consumed_at` exists and is timezone-naive, assign `timezone.utc`. If it does not exist, use `datetime.now(timezone.utc)`.
- **ADD**: `# TODO: Phase 2 - Update 12:00 PM default to accommodate timezone rollover edge cases.`
- **VALIDATE**: `uv run ruff check src/agents/nodes/calculate_log_node.py`

### 6. UPDATE `tests/unit/test_input_parser.py`
- **IMPLEMENT**: Fix any broken tests that relied on `target_date`. Add a test mimicking the LLM returning a valid `consumed_at` datetime object.
- **VALIDATE**: `uv run pytest tests/unit/test_input_parser.py`

### 7. UPDATE `tests/unit/test_calculate_log_node.py`
- **IMPLEMENT**: Update the test state payloads to include `consumed_at` instead of `current_date`. Assert that the `daily_log_service.create_log_entry` mock receives the precise timestamp dictated by `consumed_at`.
- **VALIDATE**: `uv run pytest tests/unit/test_calculate_log_node.py`

---

## TESTING STRATEGY

### Unit Tests
- **Input_Node**: Test that the node correctly injects the current time string into the SystemMessage. (Mock the file read and `datetime.now()` if necessary to prevent flaky tests).
- **Calculate_Node**: Test three scenarios:
  1. `consumed_at` is provided in state -> DB hits with specific time.
  2. `consumed_at` is None -> DB hits with `datetime.now(timezone.utc)`.

### Edge Cases
- LLM outputs a timezone-naive `datetime` versus aware. The `calculate_log_node` must ensure the object has `tzinfo=timezone.utc` before passing it to the database to prevent SQLAlchemy warnings.
- Missing dates defaulting correctly across the node pipeline.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style
`uv run ruff check src/ tests/`

### Level 2: Unit Tests
`uv run pytest tests/unit -v`

### Level 3: Manual Validation
Interact with the agent via LangSmith Studio or script. Say: "I had 200g of chicken 3 hours ago." Then inspect the `DailyLog` database to verify the injected timestamp is precisely 3 hours prior to the current execution time.

---

## ACCEPTANCE CRITERIA
- [ ] Schema successfully utilizes `consumed_at` datetime parameter.
- [ ] System prompt dynamically injects server execution time.
- [ ] `calculate_log_node` parses `consumed_at` correctly or defaults to current time securely.
- [ ] Sub-node unit tests pass accurately.
- [ ] Code passes ruff validation.
- [ ] Timezone edge case denoted with a TODO comment.

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
