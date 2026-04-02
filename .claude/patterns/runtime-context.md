# Runtime Context + User Profile

## What It Is

User-specific data (`user_id`, `user_profile`) flows through the graph via LangGraph's typed `Runtime[ContextSchema]` mechanism. The bot sends context once per API call, nodes read it from `runtime.context`, and pass `user_id` as a plain string to tools. The user profile is injected into the response node's `SystemMessage` so the LLM knows who it's talking to.

## Why This Pattern

- **Typed and validated** — `ContextSchema` is a dataclass with UUID validation in `__post_init__`, catching invalid user_ids at context creation time
- **LangGraph v1 native** — `context_schema` on `StateGraph` is the official mechanism for static per-run data (as opposed to `config["configurable"]` which is untyped)
- **Separation of concerns** — user identity is not part of `AgentState` (which is for data that transforms between nodes). Context is constant for the entire run
- **Tools are framework-free** — tools accept `user_id: str`, not `RunnableConfig` or `ToolRuntime`. This makes them callable from tests, scripts, or any other context without LangGraph dependency

## Flow

```
Telegram User
    │
    ▼
Bot Gateway (bot/gateway.py)
    │  Fetches user_id from Supabase Auth
    │  Loads user_profile from DB (cached on session)
    │  Sends HTTP POST with context: {"user_id": "...", "user_profile": {...}}
    │
    ▼
LangGraph Server
    │  Deserializes context into ContextSchema dataclass
    │  Validates user_id is a valid UUID (__post_init__)
    │  Creates Runtime[ContextSchema] object
    │
    ▼
Nodes (e.g. food_search_node, commit_node)
    │  Receive runtime: Runtime[ContextSchema] as second parameter
    │  Read runtime.context.user_id
    │  Pass user_id as plain string to tools
    │
    ▼
Tools (e.g. search_food, log_food_entry)
    │  Accept user_id: str parameter
    │  Use it for DB queries (user-scoped filtering)
    │
    ▼
response_node
    │  Reads runtime.context.user_profile
    │  Injects profile into SystemMessage content
    │  LLM knows user's name, age, gender, height
```

## ContextSchema Definition

Located in `src/context.py`:

```python
@dataclass
class ContextSchema:
    user_id: str = DEFAULT_DEV_USER_ID
    user_profile: dict = field(default_factory=lambda: DEFAULT_DEV_PROFILE.copy())

    def __post_init__(self):
        try:
            uuid.UUID(self.user_id)
        except (ValueError, AttributeError):
            self.user_id = DEFAULT_DEV_USER_ID
```

Registered on the graph in `src/agents/nutritionist.py`:

```python
workflow = StateGraph(
    state_schema=AgentState,
    input_schema=InputState,
    output_schema=OutputState,
    context_schema=ContextSchema,
)
```

## Node Pattern

Nodes declare `runtime` as their second parameter. LangGraph injects it automatically.

```python
from langgraph.runtime import Runtime
from src.context import ContextSchema

async def food_search_node(state: AgentState, runtime: Runtime[ContextSchema]) -> dict:
    user_id = runtime.context.user_id
    results = await search_food.ainvoke({"query": food_name, "user_id": user_id})
    return {"search_results": results}
```

Nodes that don't need user context (e.g. `input_parser_node`, `agent_selection_node`) simply don't declare the `runtime` parameter.

## Tool Pattern

Tools accept `user_id` as a plain string — no framework dependency.

```python
@tool
async def search_food(query: str, user_id: str) -> list[dict]:
    async with get_async_db_session() as session:
        stmt = select(FoodItem).where(...)
        # user_id used for scoping estimated food queries
```

This makes tools directly callable from integration tests:

```python
results = await search_food.ainvoke({"query": "Chicken", "user_id": TEST_USER_A})
```

## Bot Pattern

The bot sends `context` as a separate top-level field in the HTTP request body — not inside `config.configurable`:

```python
body = {
    "assistant_id": ASSISTANT_ID,
    "context": {"user_id": user_id},
}
if user_profile:
    body["context"]["user_profile"] = user_profile
```

The `context` and `config.configurable` fields cannot coexist — the LangGraph server returns 400 if both are present. `thread_id` is in the URL path (`/threads/{thread_id}/runs/wait`), not in config.

## Profile Injection in Response Node

`response_node` reads the profile from runtime context and includes it in the `SystemMessage` content:

```python
def response_node(state: AgentState, runtime: Runtime[ContextSchema]) -> dict:
    context = runtime.context if runtime.context is not None else ContextSchema()
    profile = context.user_profile

    profile_section = (
        f"\nUser Profile:\n"
        f"- Name: {profile.get('name', 'Unknown')}\n"
        f"- Age: {profile.get('age', 'Unknown')}\n"
        f"- Gender: {profile.get('gender', 'Unknown')}\n"
        f"- Height: {profile.get('height_cm', 'Unknown')}cm\n"
    )

    system_message = SystemMessage(
        content=f"{system_prompt}\n{profile_section}\n---\nContext JSON:\n..."
    )
```

The `runtime.context is not None` check handles the case where the graph is invoked without context (e.g. in the `test_feedback_integration` unit test).

## Studio Fallback

When running in LangGraph Studio (no bot to inject context), `ContextSchema` uses its defaults:
- `user_id` → `DEFAULT_DEV_USER_ID` (`fbeeb45f-...`, the `dev@dev.fitpal.bot` auth user)
- `user_profile` → `DEFAULT_DEV_PROFILE` (`{"name": "Dev User", "height_cm": 175.0, ...}`)

This ensures Studio works without any manual configuration.

## Note: Context is Per-Run, Not Per-Thread

The `context` field is ephemeral — it only exists for the duration of a single run. LangGraph does not persist it between runs on the same thread. The bot re-sends `user_id` and `user_profile` on every API call from its in-memory session cache (no DB hit after the first load).

For truly persistent user-level memory across threads, LangGraph offers **Store** (`BaseStore` / `PostgresStore`). This is a future consideration — see PRD Phase 4. The current approach works because the bot already has the profile cached and attaching it to every call is essentially free.
