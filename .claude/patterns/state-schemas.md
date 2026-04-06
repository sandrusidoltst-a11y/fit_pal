# State Schemas

## What It Is

Three-tier TypedDict schema: `InputState` (public in) → `AgentState` (internal) → `OutputState` (public out). Only `messages` is exposed externally; all internal fields (`pending_food_items`, `last_action`, `pending_confirmations`, etc.) stay hidden from callers.

## Why This Pattern

- **Clean Studio UX** — `InputState` with only `messages` renders a standard chat interface in LangSmith Studio, not a full state form with every internal field
- **Encapsulation** — internal routing fields (`last_action`, `selected_food_id`) never leak to external callers (bot, tests, Studio)
- **add_messages reducer** — nodes return `{"messages": [ai_msg]}` and the reducer appends (not replaces), giving thread-based conversation memory for free
- **Minimal coupling** — callers only know about `messages`, so internal state can evolve without breaking the public API

## Schema Tiers

### InputState (public input)

```python
class InputState(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]
```

What external callers send. Bot sends:
```python
input={"messages": [{"role": "human", "content": "I had 200g chicken"}]}
```

### OutputState (public output)

```python
class OutputState(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]
```

What external callers receive. Bot reads:
```python
messages = result.get("messages", [])
response_text = messages[-1].get("content", "")
```

### AgentState (internal)

Superset of InputState/OutputState. All node-to-node data lives here:

| Field | Type | Purpose |
|---|---|---|
| `messages` | `Annotated[List[AnyMessage], add_messages]` | Conversation history (reducer: append) |
| `pending_food_items` | `List[PendingFoodItem]` | Queue of food items awaiting processing |
| `search_results` | `List[SearchResult]` | Food DB search results for selection |
| `selected_food_id` | `Optional[str]` | Chosen food ID from agent selection |
| `pending_confirmations` | `List[MacroResult]` | Batch of calculated macros awaiting HITL confirmation |
| `processing_results` | `List[ProcessingResult]` | Final feedback (LOGGED/FAILED) per item |
| `daily_log_report` | `List[QueriedLog]` | Raw logs from DB for stats/reporting |
| `last_action` | `GraphAction` | Controls conditional routing between nodes |
| `consumed_at` | `Optional[datetime]` | Timestamp for food logging |
| `start_date` / `end_date` | `Optional[date]` | Date range for stats queries |

Registered on the graph in `src/agents/nutritionist.py`:
```python
workflow = StateGraph(
    state_schema=AgentState,
    input_schema=InputState,
    output_schema=OutputState,
    context_schema=ContextSchema,
)
```

## Node Read/Write Convention

Nodes read from state via `state.get()` and return a plain dict with only the keys they changed. LangGraph merges the returned dict into the full state.

```python
async def food_search_node(state: AgentState, runtime: Runtime[ContextSchema]) -> dict:
    # Read — use .get() for safe access on Optional fields
    items = state.get("pending_food_items", [])
    food_name = items[0]["food_name"]
    user_id = runtime.context.user_id

    # Tool call
    results = await search_food.ainvoke({"query": food_name, "user_id": user_id})

    # Write — only return changed keys
    return {"search_results": results}
```

**Reducer behavior:**
- `messages` uses `add_messages` — new messages are **appended** to existing list
- All other fields are **last-write-wins** — returned value replaces the current value

## Key Supporting Types

All defined in `src/agents/state.py` as TypedDicts:

- **`PendingFoodItem`** — food item from user input (`food_name`, `amount`, `unit`, `original_text`)
- **`SearchResult`** — DB search result (`id`, `name`, `source`)
- **`MacroResult`** — calculated macros pending confirmation (`food_name`, `amount_g`, `calories`, `protein`, `carbs`, `fat`, `source`, `food_id`)
- **`ProcessingResult`** — extends PendingFoodItem with `status` (LOGGED/FAILED) and `message`
- **`QueriedLog`** — raw daily log from DB for reporting
- **`GraphAction`** — Literal union (`LOG_FOOD`, `QUERY_DAILY_STATS`, `SELECTED`, `NO_MATCH`, `CONFIRMED`, etc.) controlling routing

## Rules

- Never add internal fields to `InputState` or `OutputState` — they are the public API
- Never return the full state dict from a node — only the keys that changed
- Use `state.get("key")` not `state["key"]` for Optional fields to avoid KeyError
- New state fields belong in `AgentState` unless they genuinely need external exposure
- Supporting types (PendingFoodItem, MacroResult, etc.) are TypedDicts, not Pydantic models — they live in state, not in LLM structured output
