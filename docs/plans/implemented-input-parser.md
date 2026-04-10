# Feature: Input Parser Node & State Management

## Feature Description
Implement the **Input Parser Node**, which acts as the entry point for the LangGraph agent. This node is responsible for parsing natural language user input into structured commands (Pydantic models) using an LLM.

Crucially, this plan also establishes the **State Management Architecture** using LangGraph's `Checkpointer` pattern to ensure user data (like daily macro totals) is persisted across conversation turns.

## User Story
**As a user**, I want to describe my meals naturally (e.g., "I had pasta with cheese"),
**So that** the agent can understand exactly what I ate without me searching for individual items manually.

## Problem Statement
1.  **Ephemeral State**: Currently, the agent forgets data once a turn ends. We need persistence.
2.  **Unstructured Input**: The agent cannot currently distinguish between "logging food" and "chitchat", nor can it break down complex meals (like "pasta with sauce") into queryable components.

## Solution Statement
1.  **Enhanced State (`AgentState`)**: Update the state schema to hold `pending_food_items` (for processing) and `daily_totals` (persisted).
2.  **Input Parser Node**: A dedicated LLM node that outputs a **list of items** to allow decomposing complex meals.
3.  **Persistence**: Integrate `SqliteSaver` as a checkpointer to save state to disk between turns.

---

## IMPLEMENTATION PLAN

### Phase 1: State & Architecture Foundation

**Objective**: Establish the data structures and memory persistence needed for the agent to "remember" and "hold" data.

**Tasks:**

#### 1. UPDATE `src/agents/state.py`
- **Goal**: Add fields to hold the parser's output and persist daily stats.
- **Action**: Update `AgentState` TypedDict.
- **New Fields**:
    - `pending_food_items`: `List[dict]` (Queue for food items waiting to be looked up)
    - `daily_totals`: `dict` (Keeps track of kcals/macros for the user)
    - `last_action`: `str` (Used by the router to decide next steps)
- **Validation**: Ensure `TypedDict` structure is valid.

#### 2. UPDATE `src/agents/nutritionist.py` (Persistence)
- **Goal**: Enable the graph to save state to a SQLite file.
- **Action**:
    - Import `SqliteSaver` from `langgraph.checkpoint.sqlite`.
    - Initialize `memory = SqliteSaver(conn)`.
    - Pass `checkpointer=memory` to `workflow.compile()`.
- **Note**: This solves the "memory loss" issue discussed.

#### 3. CREATE `src/models/input_schema.py`
- **Goal**: Define the structure that the LLM *must* output.
- **Action**: Create Pydantic models.
    - `ActionType` (Enum): `LOG_FOOD`, `QUERY_FOOD_INFO`, `QUERY_DAILY_STATS`, `CHITCHAT`.
    - `SingleFoodItem`: 
        - `food_name`: str (Normalized name for DB lookup)
        - `quantity`: str (e.g. "200g")
        - `original_text`: str
    - `FoodIntakeEvent`: 
        - `action`: ActionType
        - `items`: List[SingleFoodItem]
        - `meal_type`: str
        - `date`: datetime.date
        - `time`: datetime.time
- **Reasoning**: This allows the parser to handle "Pasta with cheese" by returning a list of **two** items, satisfying the requirement to decompose meals.

### Phase 2: Logic & Prompt Engineering

**Objective**: Create the "Brain" of the parser that understands nutrition context.

**Tasks:**

#### 4. CREATE `prompts/input_parser.md` (System Prompt)
- **Goal**: Define the rules for the LLM.
- **Key Instructions**:
    - **Decomposition**: "Pasta with cheese" -> ["Pasta", "Cheese"].
    - **Normalization**: "Big Mac" -> "Hamburger". "White Bread" -> "White Bread" (Specific) OR "Bread" (Generic).
    - **Extraction**: Infer `meal_type` (Breakfast/Lunch/Dinner) from context or time.
    - **Few-Shot Examples**:
        - Input: "I ate a Big Mac" -> Output: `food_name="Hamburger"` (or similar DB-friendly term).
        - Input: "3 slices of white bread" -> Output: `food_name="White Bread"`.

#### 5. IMPLEMENT `src/agents/nodes/input_node.py`
- **Goal**: The actual Python function that calls the LLM.
- **Action**:
    - Load the prompt from `prompts/input_parser.md`.
    - Use `ChatOpenAI` or `ChatAnthropic` with `.with_structured_output(FoodIntakeEvent)`.
    - Function `input_parser_node(state: AgentState)`:
        - Get last user message.
        - Invoke LLM.
        - Return `{"pending_food_items": result.items, "last_action": result.action}`.

### Phase 3: Integration

**Objective**: Connect the new node to the graph.

**Tasks:**

#### 6. UPDATE `src/agents/nutritionist.py` (Graph Definition)
- **Goal**: Add the new node to the workflow.
- **Action**:
    - `workflow.add_node("input_parser", input_parser_node)`
    - Set `input_parser` as the **entry point**.
    - Add Conditional Edge:
        - If `action == LOG_FOOD` or `QUERY_FOOD_INFO`, go to `food_lookup`.
        - Else, go to `response`.

---

## VALIDATION COMMANDS

### 1. Test the Schema
`uv run python -c "from src.models.input_schema import FoodIntakeEvent; print(FoodIntakeEvent.model_json_schema())"`

### 2. Test the Node (Unit Logic)
Create a temporary test script `tests/verify_input_logic.py` that mocks the State and calls `input_parser_node`.
