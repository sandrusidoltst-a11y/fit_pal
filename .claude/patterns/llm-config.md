# LLM Configuration + Pydantic Output

## What It Is

Every LLM call inside the FitPal graph goes through one factory: `get_llm_for_node(node_name)` in [src/config.py](../../src/config.py). Nodes never instantiate `ChatOpenAI`, `ChatAnthropic`, or `init_chat_model` directly. They ask the factory by name, receive a configured LLM instance, optionally wrap it with `.with_structured_output(Schema)`, and `await` the result.

The factory composes its return value from three layers, in order of precedence:

1. **Hardcoded defaults** inside `get_llm_for_node` itself (`temperature=0.0`, `model_provider=GLOBAL_PROVIDER`, `model=GLOBAL_MODEL`).
2. **Global environment variables** (`LLM_PROVIDER`, `LLM_MODEL_NAME`) loaded from `.env` at import time into `GLOBAL_PROVIDER` and `GLOBAL_MODEL`.
3. **Per-node overrides** from `NODE_CONFIGS`, a dict mapping node name → kwargs that get unpacked into `init_chat_model`.

The merged dict is passed via `**kwargs` into LangChain's universal `init_chat_model`, which routes to the right provider class (`ChatOpenAI`, `ChatAnthropic`, etc.) automatically based on `model_provider`. This means a single env var (`LLM_PROVIDER=anthropic`) would swap every node in the graph to a different provider with no code changes — provided the per-node `NODE_CONFIGS` entries don't pin a specific provider.

The pattern's other half is **structured output**. Every node that needs typed data from the LLM uses `.with_structured_output(SomeSchema)` where `SomeSchema` is a Pydantic v2 model defined in `src/schemas/`. The LLM returns an instance of the Pydantic model directly — no JSON parsing, no string handling, no `try/except` around `json.loads`. Field access is `result.action`, not `result["action"]`. Conversion to a plain dict happens only when the value crosses into LangGraph state via `.model_dump()`, and only at that boundary.

There is exactly one exception to the structured-output rule: `response_node`. It generates conversational free-text replies and calls `await llm.ainvoke(...)` directly without a schema. That carve-out is documented below.

## Why This Pattern

- **One place to swap a model.** Changing the global default model is `LLM_MODEL_NAME=gpt-4o` in `.env`. Changing one node's model is a one-line edit to `NODE_CONFIGS`. Neither change touches any node code, any test, or any prompt. Without this factory, swapping a model meant grepping for `ChatOpenAI(model="...")` across half the codebase and editing in lockstep — and we already lived through that (see `commit_logs/2026-02-21_21-00-14_refactor-llm-configuration.md`).

- **Per-node temperature control without scattering magic numbers.** Some nodes need deterministic output (input parsing at `temperature=0.0`); others need warmth (response generation at `temperature=0.7`). Both live next to each other in `NODE_CONFIGS` so the contrast is visible at a glance. A reviewer can verify in two seconds that no parsing node has accidentally been set to `0.7`.

- **Provider-agnostic by design.** `init_chat_model` is LangChain's universal initializer — it accepts a `model_provider` string and routes to the correct concrete class. We currently run on OpenAI, but the architecture is set up so that swapping to Anthropic, Google, Mistral, or a local model is a config change, not a refactor. This is not theoretical — the eval notebooks already exercise different models for the judge LLM.

- **`.with_structured_output()` makes Pydantic the contract between LLM and code.** Instead of "the LLM returns a JSON string and we hope it parses", the contract is "the LLM returns an instance of `FoodIntakeEvent` or it raises". The Pydantic model is the schema definition, the validation layer, the IDE autocomplete source, and the LangSmith trace shape — all from one declaration. There's no second source of truth for "what fields does the LLM return".

- **Field access stays pythonic.** `result.action.value` and `result.items[0].food_name` are unambiguous — they fail loudly at access time if the schema drifts, the IDE knows the types, and refactor tooling (rename a field) updates every callsite. None of that works with `result["action"]` or `json.loads(text)["action"]`.

- **Tests mock at exactly one seam.** Every unit test for an LLM-using node patches `src.agents.nodes.<module>.get_llm_for_node` and returns a `MagicMock` whose `.with_structured_output(...).ainvoke(...)` returns the desired Pydantic instance. There is no need to mock provider classes, no need to mock `init_chat_model`, no need to mock HTTP. The factory is the seam, and it's the same seam in every test. See [.claude/skills/test-engineering/references/unit-testing.md](../skills/test-engineering/references/unit-testing.md) for the canonical pattern.

## The Configuration Hierarchy

`get_llm_for_node` lives in [src/config.py:47-72](../../src/config.py#L47-L72). The full flow:

```python
def get_llm_for_node(node_name: str):
    # Layer 1 — hardcoded defaults
    params: dict[str, Any] = {
        "model_provider": GLOBAL_PROVIDER,   # from env, fallback "openai"
        "model": GLOBAL_MODEL,                # from env, fallback "gpt-4.1-nano"
        "temperature": 0.0,
    }

    # Layer 2 — overlay node-specific config
    node_config = NODE_CONFIGS.get(node_name, NODE_CONFIGS.get("default", {}))
    params.update(node_config)

    # Layer 3 — alias normalisation (provider → model_provider)
    if "provider" in params:
        params["model_provider"] = params.pop("provider")

    return init_chat_model(**params)
```

Reading top-to-bottom:

1. **Start with safe defaults.** Provider and model come from environment variables loaded at module import time:
   ```python
   GLOBAL_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
   GLOBAL_MODEL = os.getenv("LLM_MODEL_NAME", "gpt-4.1-nano")
   ```
   `temperature=0.0` is the conservative default — most nodes are parsing nodes that should be deterministic. Nodes that want warmth must opt in.

2. **Look up the node's overrides.** `NODE_CONFIGS.get(node_name, ...)` falls back to `NODE_CONFIGS["default"]` if the node name isn't registered. The default itself only sets `temperature=0.0`, so an unregistered node ends up with the same config as a registered parsing node — no surprises.

3. **`.update()` overlays the dict.** Any key the node config sets wins over the default. Any key it doesn't set stays at the default. This is why the node config dict is intentionally sparse — `{"temperature": 0.7}` for `response_node` overrides only the temperature and inherits provider+model from the global defaults.

4. **Alias normalisation.** Historically the per-node config used the key `"provider"`, but `init_chat_model` expects `"model_provider"`. The factory pops `"provider"` and re-inserts it under the correct name so both spellings work in `NODE_CONFIGS`. This is a small ergonomic affordance — the kind of thing that would otherwise cause a confusing `TypeError: init_chat_model() got an unexpected keyword argument 'provider'`. See "The `provider` → `model_provider` Alias" below for the gotcha rationale.

5. **Unpack into `init_chat_model`.** The merged dict gets passed via `**params`. LangChain's universal initializer handles the rest: it picks the right provider class, forwards `temperature`, `max_tokens`, `stop`, `timeout`, `max_retries`, and any other kwargs the provider supports. Full kwarg list: https://python.langchain.com/docs/how_to/chat_models_universal_init/.

The full `NODE_CONFIGS` dict from [src/config.py:37-45](../../src/config.py#L37-L45):

```python
NODE_CONFIGS = {
    "input_node":          {"temperature": 0.0},
    "selection_node":      {"temperature": 0.0},
    "estimation_node":     {"temperature": 0.0},
    "confirmation_node":   {"temperature": 0.0},
    "response_node":       {"temperature": 0.7},
    "personal_stats_node": {"temperature": 0.0},
    "default":             {"temperature": 0.0},
}
```

Note that none of the entries set `model` or `provider` — every node uses the global defaults. The only thing that varies per node is temperature, and only `response_node` differs. This is deliberate: in production we want every node running the same model so that quality experiments are easy to set up (change one env var, run the eval, revert). If we ever want to run `selection_node` on a stronger model than `input_node`, the override goes here as `{"temperature": 0.0, "model": "gpt-4o"}` and nothing else changes.

## Adding a New Node to NODE_CONFIGS

The rule is precise:

> **Add an entry to `NODE_CONFIGS` if and only if your node needs a non-default config OR you want the node name to appear in the file for visibility.**

A new parsing node at `temperature=0.0` does not technically need an entry — it would inherit `"default"` and behave identically. But adding it anyway is preferred for two reasons:

1. **Discoverability.** Reading `NODE_CONFIGS` should give you a complete inventory of LLM-calling nodes in the graph. If a node is missing, a reviewer might wonder whether it was forgotten or whether it intentionally relies on the default — and that's a question they shouldn't have to ask.
2. **Forward-compatibility.** When you eventually need to tune the temperature for that node, the entry already exists; you change `0.0` → `0.3` and you're done. Without the entry, you'd add it under pressure during a debugging session.

So in practice every LLM-using node in the graph has an entry, and the file functions as both config and documentation. Don't break that pattern.

## Pydantic Structured Output

This is the second half of the pattern, and the more important half in day-to-day work. Every node that needs typed data from an LLM follows this exact flow:

```python
llm = get_llm_for_node("input_node")
structured_llm = llm.with_structured_output(FoodIntakeEvent)
result = await structured_llm.ainvoke(messages)
# result is now a FoodIntakeEvent instance — access fields as attributes
```

`.with_structured_output(Schema)` is a LangChain method that takes a Pydantic v2 model class and returns a wrapped LLM whose `.ainvoke(...)` is guaranteed to return an instance of that model (or raise). Under the hood, LangChain converts the Pydantic schema into a JSON schema, attaches it to the LLM call as a tool/function definition, and parses the LLM's response back into an instance of the model. From the node's perspective, none of that machinery is visible — you pass `messages`, you get back a typed object.

Every schema lives in `src/schemas/`, one file per node:

| Schema file | Pydantic class | Used by | Purpose |
|---|---|---|---|
| `input_schema.py` | `FoodIntakeEvent` | `input_node` | Parses raw user message into action + items + dates |
| `selection_schema.py` | `FoodSelectionResult` | `selection_node` | Picks the best matching food from search results |
| `estimation_schema.py` | `MacroEstimation` | `calculate_macros_node` (off-menu path) | LLM-estimated calories/protein/carbs/fat |
| `confirmation_schema.py` | `ConfirmationResponse` | `confirmation_node` | Parses HITL confirm/reject/edit response |
| `personal_stats_schema.py` | `PersonalStatExtraction` | `personal_stats_node` | Extracts stat type + value (weight/body fat) |

Real example from [src/agents/nodes/input_node.py:23-50](../../src/agents/nodes/input_node.py#L23-L50):

```python
async def input_parser_node(state: AgentState):
    llm = get_llm_for_node("input_node")
    structured_llm = llm.with_structured_output(FoodIntakeEvent)

    last_message = state["messages"][-1]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    system_prompt_with_time = f"The current system time is: {now_str}\n\n{_SYSTEM_PROMPT}"

    messages = [
        SystemMessage(content=system_prompt_with_time),
        last_message,
    ]

    result = await structured_llm.ainvoke(messages)

    logger.info("Input parsed", action=result.action.value, items=len(result.items))

    return {
        "pending_food_items": [item.model_dump() for item in result.items],
        "last_action": result.action.value,
        "processing_results": [],
    }
```

A few things to notice:

- `result.action.value` and `result.items` are pythonic attribute access. `action` is an `Enum`, so `.value` gets the string. The IDE knows the types because Pydantic generates them.
- `[item.model_dump() for item in result.items]` is the **only** `.model_dump()` call in the node, and it happens at the boundary where the data gets written into LangGraph state. State stores plain dicts (because state must be JSON-serializable for the checkpointer), so the Pydantic objects get flattened to dicts here and only here.
- The `result` object itself is never `.model_dump()`'d. We don't need the whole thing in state — only the `items` list does, and we expand it inline.

This is the key nuance: `.model_dump()` is **not** "the thing you call after `.with_structured_output()`". It's "the thing you call when you cross from the Pydantic world into the dict-shaped state world". In four out of five structured-output nodes, the conversion isn't needed at all — the node reads attributes off the result, makes branching decisions, and constructs a new dict for the state update by hand. See [src/agents/nodes/personal_stats_node.py:43-56](../../src/agents/nodes/personal_stats_node.py#L43-L56) for the cleanest example: it extracts `result.stat_type` and `result.value`, calls a tool, and builds a dict literal — no `.model_dump()` anywhere.

### When `.model_dump()` is the right call

- The Pydantic instance (or a child of it) is about to be written to a state field whose type is a `dict` or `list[dict]`. Example: `pending_food_items: List[dict]` in `AgentState`, populated from `[item.model_dump() for item in result.items]`.
- The instance needs to be logged, serialized to JSON, or sent over HTTP, and the receiver expects a dict.

### When `.model_dump()` is the wrong call

- You're about to pass the result to another Python function that accepts the Pydantic type. Pass the instance, not the dict.
- You're branching on a field (`if result.action == Action.LOG_FOOD:`). Read the attribute directly.
- You're constructing a new dict literal anyway, picking only some fields. Index/access individual attributes; don't dump the whole thing and re-pick.

## The Conversational Carve-Out: `response_node`

`response_node` is the only node in the graph that calls the LLM **without** structured output. From [src/agents/nodes/response_node.py:115-118](../../src/agents/nodes/response_node.py#L115-L118):

```python
llm = get_llm_for_node("response_node")
result = await llm.ainvoke(full_messages)
return {"messages": [result]}
```

Notice three things this node does **not** do:

- It does not call `.with_structured_output(...)`.
- It does not import a schema from `src/schemas/`.
- It does not call `.model_dump()`. The `result` is an `AIMessage` object, and it's appended directly to the `messages` field in state — LangGraph's `add_messages` reducer knows how to merge `AIMessage` objects into the message history.

This is the only justified exception to the "always use structured output" rule. The reason: `response_node`'s job is to produce a conversational reply for the user. There is no schema for "a friendly nutrition coach response" — the output is free-form natural language, and forcing it through a Pydantic shape would either constrain the LLM's expressiveness (`{"reply": str}` is just a wrapper around the same string) or invent fake structure that no downstream code consumes.

The carve-out is also why `response_node` is the only node with `temperature=0.7` in `NODE_CONFIGS`. Conversational responses benefit from variability; parsing nodes do not.

If you ever add another conversational node (e.g. a clarification-question generator), it follows the same shape: `get_llm_for_node(...)` for the instance, `await llm.ainvoke(messages)` for the call, return the `AIMessage` directly into `messages`. No schema, no `.model_dump()`. Bump the temperature in `NODE_CONFIGS` if you want warmth.

## Prompts Live in `prompts/`, Loaded at Module Import

Every system prompt lives in a `.md` file under `prompts/` at the project root, and is loaded **once** at module import time using `BASE_DIR` from `src/config.py`. Loading prompts at call time inside an async node is forbidden — it caused a class of `BlockingError` bugs in early FitPal that took a full RCA to resolve.

The canonical pattern, from [src/agents/nodes/input_node.py:13-20](../../src/agents/nodes/input_node.py#L13-L20):

```python
import os
from src.config import BASE_DIR

# Load prompt once at import time — no file I/O during graph execution
_PROMPT_PATH = os.path.join(BASE_DIR, "prompts", "input_parser.md")
try:
    with open(_PROMPT_PATH, "r", encoding="utf-8") as _f:
        _SYSTEM_PROMPT = _f.read()
except FileNotFoundError:
    logger.warning("Prompt file not found, using fallback", path=_PROMPT_PATH)
    _SYSTEM_PROMPT = "You are a helpful nutrition assistant. Parse food intake."
```

Three rules in this snippet:

1. **`BASE_DIR` from `src/config.py`, not `os.getcwd()`.** `BASE_DIR` is computed once at config import time as `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`. It's a constant. `os.getcwd()` is a syscall that the `blockbuster` library (used by LangGraph to detect blocking I/O in async paths) flags as a blocking operation when called inside an async node. Five FitPal nodes were calling `os.getcwd()` inside async bodies and crashing the server with `BlockingError` until the fix was rolled out. The RCA is at `docs/rca/blocking-error-os-getcwd-in-async-nodes.md`. **Always use `BASE_DIR`. Never use `os.getcwd()`.**

2. **`open()` happens at module level (inside `_PROMPT_PATH` block), not inside the node function.** Module-level code runs once when Python imports the file — typically at server startup, before any request handling. Reading a file at startup is fine; the event loop isn't spinning yet. Reading the same file inside `async def some_node(...)` would block the loop on every call.

3. **`try/except FileNotFoundError` with a fallback string.** The graph must still boot in environments where the prompts directory isn't on disk (e.g. unusual test setups, partial Docker builds). The fallback is intentionally minimal — just enough for the LLM to have *some* system prompt. The `logger.warning` makes the situation visible without raising.

The variable holding the prompt is module-private (`_SYSTEM_PROMPT` with the underscore prefix). It is never reassigned inside the node — if a node needs to compose a per-call prompt (e.g. injecting the current timestamp, like `input_parser_node` does), it builds a new string from `_SYSTEM_PROMPT` inside the function body.

The full list of prompts in `prompts/`:

| File | Loaded by |
|---|---|
| `input_parser.md` | `input_node` |
| `agent_selection.md` | `selection_node` |
| `macro_estimation.md` | `calculate_macros_node._estimate_macros` |
| `confirmation_parser.md` | `confirmation_node` |
| `personal_stats_extractor.md` | `personal_stats_node` |
| `response_generator.md` | `response_node` |
| `lookup.md`, `tool_lookup.md` | (legacy — no current loader) |

Cross-reference: [async-patterns.md](async-patterns.md) covers `BlockingError`, `blockbuster`, and the broader "no sync I/O in async nodes" rule that this section is one corner of.

## The `provider` → `model_provider` Alias

A small but real gotcha lives in [src/config.py:68-70](../../src/config.py#L68-L70):

```python
if "provider" in params:
    params["model_provider"] = params.pop("provider")
```

The reason this exists: `init_chat_model`'s actual parameter is `model_provider`, but it's natural to write `{"provider": "anthropic"}` in `NODE_CONFIGS` because the global env var is named `LLM_PROVIDER`. Without this normalisation, the first time someone added `{"provider": "anthropic"}` to a node config they would get:

```
TypeError: init_chat_model() got an unexpected keyword argument 'provider'
```

…with no obvious hint about what the right key name is. The alias makes both spellings work. It's a small ergonomic fix that prevents a frustrating class of errors.

If you're adding a new entry to `NODE_CONFIGS` and want to override the provider for that node, **either spelling is correct**:

```python
"selection_node": {"temperature": 0.0, "provider": "anthropic", "model": "claude-sonnet-4-5"}
# or
"selection_node": {"temperature": 0.0, "model_provider": "anthropic", "model": "claude-sonnet-4-5"}
```

The first form is shorter and matches the env var name; the second matches the underlying LangChain API. We have no strong preference, but consistency within the file is nice.

## When `get_llm_for_node` Is the Wrong Choice

The factory governs LLM instantiation **inside the production graph**. There are two contexts where bypassing it is correct:

1. **Eval notebooks (`notebooks/evals/*.ipynb`).** The judge LLM in a LangSmith evaluation is intentionally a different (typically stronger) model than the node under test. You instantiate it directly with `init_chat_model("gpt-4o", temperature=0).with_structured_output(JudgeSchema)`. The whole point of the judge is that it does not share configuration with the production node — wiring it through `NODE_CONFIGS` would conflate the two and make eval results meaningless. Real example: `notebooks/evals/eval_input_parser.ipynb:507`.

2. **Ad-hoc scripts and one-shot debugging.** A script under `src/scripts/` that needs a quick LLM call (e.g. backfilling a column with LLM-generated tags) can instantiate `init_chat_model` directly. These scripts run outside the graph, are not exposed to LangGraph state, and have no node identity to look up. Forcing them to register a fake `NODE_CONFIGS` entry would be cargo-culting.

Both exceptions share a property: they are not part of the LangGraph runtime. The factory exists to ensure every node in the graph runs with consistent, reviewable, swappable configuration; that guarantee doesn't apply to code outside the graph.

If you find yourself wanting to bypass `get_llm_for_node` from inside `src/agents/nodes/`, **stop and reconsider**. You almost certainly want to add a new entry to `NODE_CONFIGS` instead.

## Cross-References

- **[tool-first.md](tool-first.md)** — the parallel pattern for the *other* major thing nodes do (talk to the DB). Tool-first governs `await tool.ainvoke(...)`; this doc governs `await structured_llm.ainvoke(...)`. Together they describe the entire surface a node touches outside its own state.
- **[async-patterns.md](async-patterns.md)** — explains why prompt loading must happen at module import and not inside the node body, and why every LLM call uses `await llm.ainvoke(...)` instead of `llm.invoke(...)`. The `BlockingError` history that motivated the `BASE_DIR` rule lives there.
- **[state-schemas.md](state-schemas.md)** — explains how Pydantic-output dicts (after `.model_dump()`) get merged into `AgentState` fields. The shapes in `src/schemas/` have to be compatible with the state shapes in `src/agents/state.py`.

## Rules

Hard rules. Violating any of these is a bug.

1. **Never instantiate an LLM directly inside `src/agents/nodes/`.** No `ChatOpenAI(...)`, no `ChatAnthropic(...)`, no `init_chat_model(...)`. The only correct call is `get_llm_for_node("<node_name>")`. Grep `src/agents/nodes/` for `init_chat_model` or `ChatOpenAI` — the result must be empty.

2. **Never hardcode a model name in a node.** Model selection lives in `NODE_CONFIGS` and `LLM_MODEL_NAME`, nowhere else. If you find yourself writing `"gpt-4o"` inside a node body, stop and add an override to `NODE_CONFIGS` instead.

3. **Every LLM-using node in the graph has an entry in `NODE_CONFIGS`**, even if the entry is just `{"temperature": 0.0}` — for discoverability and forward-compatibility.

4. **Use `.with_structured_output(Schema)` for any node that needs typed data from the LLM.** The schema is a Pydantic v2 model in `src/schemas/`. The only exception is conversational/output nodes that produce free-text replies (currently only `response_node`).

5. **Never parse raw LLM strings.** No `json.loads(response.content)`. No `re.search(...)` over `response.content`. No string-splitting on LLM output. If you need structure, use `.with_structured_output(...)`. If you need free text, use `await llm.ainvoke(...)` and treat the result as an `AIMessage`.

6. **Access structured-output fields as Python attributes**, not dict keys. `result.action`, not `result["action"]`. The Pydantic instance is the contract; treat it like one.

7. **Call `.model_dump()` only at the state-write boundary**, when converting a Pydantic object to a JSON-serializable dict for storage in `AgentState`. Never call `.model_dump()` "just in case" or because "that's what the rule says". Read attributes directly when branching, logging, or passing to other Python functions.

8. **Load prompts at module import time using `BASE_DIR`.** Never inside an async node body, never with `os.getcwd()`. The prompt variable is module-private (`_SYSTEM_PROMPT`) and is read-only after import.

9. **Wrap prompt loading in `try/except FileNotFoundError` with a fallback string** so the graph still boots when prompts are missing. Log a warning so the missing file is visible.

10. **Mock at the `get_llm_for_node` seam in unit tests.** `patch("src.agents.nodes.<module>.get_llm_for_node")`. Never mock `init_chat_model`, never mock provider classes, never mock HTTP. The factory is the seam, and it's the same seam in every node test.

11. **Eval notebooks and ad-hoc scripts may bypass `get_llm_for_node`.** Code inside `src/agents/nodes/` may not.

12. **The `provider` and `model_provider` keys are interchangeable in `NODE_CONFIGS`.** The factory normalises `provider` → `model_provider` before passing to `init_chat_model`. Use whichever spelling reads better in context, but be consistent within a single config entry.
