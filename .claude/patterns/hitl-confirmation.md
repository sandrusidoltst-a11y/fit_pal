# HITL Batch Confirmation

## What It Is

When a user logs food, FitPal accumulates every parsed item into a *batch* of macro previews held entirely in graph state. The batch never touches the database. Once all items have been processed, [confirmation_node](../../src/agents/nodes/confirmation_node.py) presents the whole batch to the user as a single review payload, pauses the graph with `interrupt()`, parses the user's natural-language reply with an LLM, and routes the graph dynamically via `Command(goto=...)` to either `commit` (write everything) or `response` (cancel everything). Edits modify the in-state batch in place and re-enter the interrupt loop, so the user can refine the batch as many times as they want before any DB write happens.

The pattern has four moving parts:

1. **Accumulation**: `calculate_macros_node` appends `MacroResult` previews to `pending_confirmations` for every item, looping back through `food_search` until `pending_food_items` is empty.
2. **The interrupt loop**: `confirmation_node` runs `while True: interrupt(preview); decision = await _parse_confirmation(...)` and handles three branches based on the parsed decision.
3. **Dynamic routing via `Command`**: `confirmation_node` returns `Command[Literal["commit", "response"]]` instead of a state-update dict, so the *next node is decided at runtime from the user's answer*, not by static graph edges.
4. **Commit-or-discard**: Only `commit_node` writes to the DB. Reject and edit-loops never persist anything. The batch lives in `pending_confirmations` from the moment `calculate_macros_node` builds it until the moment `commit_node` or `confirmation_node` clears it.

This is the only place in the FitPal graph where a node can pause multiple times in a single execution, the only place that uses LangGraph's `interrupt()`, and the only place that returns `Command` instead of a dict. Everything else in the graph is a one-shot node-to-edge flow.

## Why This Pattern

- **Atomicity from the user's perspective.** A message like "I had chicken, rice, and broccoli" is one mental act. Asking "should I log the chicken?" → "should I log the rice?" → "should I log the broccoli?" would be insufferable. Batching the confirmation means one yes/no covers everything the user said in one breath, which matches how people actually think about meals.

- **Reversibility before persistence.** The user sees the exact macros — calories, protein, carbs, fat, *with* an `(estimated)` tag for items that came from LLM estimation rather than the DB — *before* anything hits Postgres. There is no "oops, that wasn't what I meant" requiring a delete query, because nothing was written. The DB only learns about food items the user has explicitly approved.

- **Conversational edits, not menus or buttons.** The user can write "change the rice to 200g" or "remove the broccoli" in plain English. The LLM parses that into structured `ItemEdit` operations against the in-memory batch. There are no inline keyboards, no item IDs to remember, no "tap to edit" — the interaction stays in the same channel as the original log message. This is critical for a Telegram-first product where the interface is a text input box.

- **Trust calibration for estimation.** The two-tier food path (DB hit → use database; DB miss → ask the LLM to estimate) means some items in the batch are authoritative and some are guesses. The `(estimated)` tag in the preview makes that distinction visible at the moment the user is about to commit, so they can correct or reject estimates with full information. Without the preview, the user would have no signal that some macros were guessed.

- **`interrupt()` + `Command()` make routing dynamic.** The next node depends on what the user types in their reply, which the graph cannot know in advance. Static conditional edges (`add_conditional_edges`) decide routes from *state already in the graph* — they cannot decide based on future user input. `interrupt()` pauses execution until the user replies; the reply lands in `decision`; the `Command(goto=...)` return value picks the next node from the dynamically computed answer. This is exactly what `Command` was designed for, and it's the right tool for this job.

- **The batch lives in state, not in a side store.** `pending_confirmations` is just a `List[MacroResult]` field in `AgentState`. It gets checkpointed by LangGraph along with everything else, which means a partially-confirmed batch survives a server restart (the user's next message resumes from the interrupt). No Redis, no temp table, no in-memory dict that vanishes on restart.

## The Data Shape: `MacroResult`

The data unit that flows through the entire HITL pipeline is `MacroResult`, defined in [src/agents/state.py:79-94](../../src/agents/state.py#L79-L94):

```python
class MacroResult(TypedDict):
    food_name: str
    amount_g: float
    calories: float
    protein: float
    carbs: float
    fat: float
    source: Literal["database", "estimated"]
    original_text: str
    food_id: Optional[str]
```

Every field is in the TypedDict for a reason that the HITL pipeline depends on:

- **`food_name`, `amount_g`, `calories`, `protein`, `carbs`, `fat`** — the human-readable preview the user sees, and the values that eventually get written to a `DailyLog` row by `commit_node`. Computed once by `calculate_macros_node` and updated in place by `_apply_edits` when the user changes amounts.

- **`source`** — distinguishes "this came from the food_items table" (`"database"`) from "the LLM made this up because we had no DB match" (`"estimated"`). Drives the `(estimated)` tag in the preview, and drives the branching in `commit_node` (estimated items get persisted as new `food_items` rows with back-calculated per-100g values; DB items don't). Also drives the branching in `_apply_edits` when amounts change — see the edit pipeline section.

- **`food_id`** — `None` for estimated items (no DB row exists yet), a UUID string for DB items. This is the field that `_apply_edits` and `commit_node` actually branch on when they need to know "is this item backed by a real DB row, or do I need to fabricate one?". `source` and `food_id is not None` are correlated but `food_id` is the operational signal because it's what the tools take as a parameter.

- **`original_text`** — the literal substring the user typed for this item ("200g of grilled chicken"). Preserved through the entire pipeline so `commit_node` can store it on the `DailyLog` row, which lets later queries show "what the user actually said" alongside "what we logged". Never used by the HITL flow itself, but the HITL flow has to *carry* it from `calculate_macros_node` to `commit_node`, so it lives on `MacroResult`.

`MacroResult` is the shape the rest of this document refers to whenever it talks about "an item in the batch" or "the preview payload".

## Phase 1 — Accumulation: `calculate_macros_node` → `pending_confirmations`

Before `confirmation_node` can show anything, the batch has to be built. That happens in [calculate_macros_node](../../src/agents/nodes/calculate_macros_node.py), one item at a time, with a loop-back edge in the graph definition.

The relevant graph wiring from [src/agents/nutritionist.py:78-85](../../src/agents/nutritionist.py#L78-L85):

```python
def route_after_calculate_macros(state: AgentState):
    """Loop back if more items pending, else show batch for confirmation."""
    if state.get("pending_food_items", []):
        return "food_search"  # Process next item
    return "confirmation"  # All items calculated, show batch

workflow.add_conditional_edges(
    "calculate_macros",
    route_after_calculate_macros,
    {
        "food_search": "food_search",
        "confirmation": "confirmation",
    },
)
```

The loop processes items sequentially:

1. `input_parser_node` writes the full list of parsed items to `pending_food_items`.
2. `food_search_node` searches the DB for the *first* item only, writes results to `search_results`.
3. `agent_selection_node` picks the best match (or sets `selected_food_id=None` for off-menu) and routes to `calculate_macros`.
4. `calculate_macros_node` computes macros for the current item — via the `calculate_food_macros` tool if there's a DB match, or via LLM estimation (`MacroEstimation` structured output) if not — and **appends** the result to `pending_confirmations`. It pops the processed item from `pending_food_items` and returns.
5. `route_after_calculate_macros` checks: more items pending? loop back to `food_search`. Otherwise, route to `confirmation`.

Two things are worth highlighting here:

- **The accumulation is purely additive.** `calculate_macros_node` does not look at existing `pending_confirmations` to decide what to do — it just appends. This makes the per-item code trivially simple and means each item gets processed in isolation.
- **Nothing is written to the DB in this phase.** Even when `calculate_food_macros` runs against a real DB row, it only *reads* from the row — it doesn't create a `DailyLog`. The result is a `MacroResult` dict in state, nothing more. The DB-write boundary is `commit_node`, and `commit_node` only runs after the user confirms.

The off-menu path (LLM estimation, `source="estimated"`, `food_id=None`) is a separate concern and is documented in [off-menu-estimation.md](off-menu-estimation.md). The HITL flow doesn't care which path produced an item — it just knows it's a `MacroResult` and treats DB and estimated items uniformly until the edit pipeline, where the distinction reappears.

## Phase 2 — The Interrupt Loop in `confirmation_node`

This is the heart of the pattern. The full loop body, lightly trimmed, from [confirmation_node.py:60-128](../../src/agents/nodes/confirmation_node.py#L60-L128):

```python
async def confirmation_node(
    state: AgentState, runtime: Runtime[ContextSchema],
) -> Command[Literal["commit", "response"]]:
    batch = list(state.get("pending_confirmations", []))

    if not batch:
        logger.warning("Confirmation node called with empty batch, skipping to response")
        return Command(goto="response")

    preview = _format_batch_preview(batch)

    while True:
        user_response = interrupt(preview)
        decision = await _parse_confirmation(user_response, batch)

        if decision.action == "confirm":
            return Command(
                goto="commit",
                update={
                    "pending_confirmations": batch,
                    "last_action": "CONFIRMED",
                },
            )

        elif decision.action == "reject":
            failed_results = [
                {
                    "food_name": item["food_name"],
                    "amount": item["amount_g"],
                    "unit": "g",
                    "original_text": item["original_text"],
                    "status": "FAILED",
                    "message": f"User rejected logging {item['food_name']}",
                    "source": item.get("source"),
                }
                for item in batch
            ]
            return Command(
                goto="response",
                update={
                    "last_action": "REJECTED",
                    "pending_confirmations": [],
                    "processing_results": state.get("processing_results", []) + failed_results,
                },
            )

        elif decision.action == "edit":
            batch = await _apply_edits(batch, decision.edits or [])
            preview = _format_batch_preview(batch)
            # Loop continues → interrupt again with updated preview
```

Walking through what each piece does:

### `interrupt(preview)` pauses the graph

`interrupt()` is a LangGraph primitive that suspends execution at the call site, surfaces its argument (`preview`) as the interrupt value on the run, and waits for the run to be resumed externally. From inside the node, `interrupt(preview)` looks like a function that "returns" the user's reply — but only after the run has been resumed via `command={"resume": "<user text>"}` from the bot or test harness. Until then, the graph is paused, the checkpointer has snapshotted the state including the in-loop `batch` variable's effect on local execution, and the server is doing nothing for this thread.

The argument to `interrupt()` is whatever you want the bot/UI to see while the graph is paused. In FitPal it's the dict produced by `_format_batch_preview`:

```python
{
    "question": "Please review the following items before I log them. ...",
    "items": [
        {"index": 0, "description": "chicken — 200g", "calories": 330, ...},
        {"index": 1, "description": "rice — 150g (estimated)", "calories": 195, ...},
    ],
    "totals": {"calories": 525, "protein": ..., "carbs": ..., "fat": ...},
}
```

The bot reads this dict from the thread state, formats it for Telegram (the human-readable rendering lives in the bot, not the graph), and sends it as a message. The graph itself is provider-agnostic — `interrupt()` doesn't know about Telegram, and the dict shape is independent of how it eventually reaches the user.

### `_parse_confirmation` interprets the user's reply

Once the run is resumed, `interrupt(preview)` returns the resume value (the user's text). That text goes to `_parse_confirmation`, which is a small LLM call using the standard structured-output pattern (see [llm-config.md](llm-config.md)):

```python
async def _parse_confirmation(user_text: str, batch: list[MacroResult]) -> ConfirmationResponse:
    batch_context = "\n".join(
        f"[{i}] {item['food_name']} — {item['amount_g']}g ({item['source']})"
        for i, item in enumerate(batch)
    )
    system_prompt = _CONFIRMATION_PROMPT.replace("{batch_context}", batch_context)

    llm = get_llm_for_node("confirmation_node")
    structured_llm = llm.with_structured_output(ConfirmationResponse)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_text),
    ]

    return await structured_llm.ainvoke(messages)
```

Two design choices to notice:

1. **The current batch is injected into the system prompt** as `{batch_context}`. The LLM needs to know what items exist (and their indices) to produce valid `ItemEdit` operations like `{item_index: 1, edit_type: "change_amount", new_amount_g: 200}`. The prompt template lives in `prompts/confirmation_parser.md`; injection happens via `.replace("{batch_context}", ...)`. Module-level prompt loading still applies — see the prompt-loading section of [llm-config.md](llm-config.md) for why this prompt is loaded once at import time and not re-read on every call.

2. **The output is a Pydantic `ConfirmationResponse`**, defined in [src/schemas/confirmation_schema.py](../../src/schemas/confirmation_schema.py):

   ```python
   class ConfirmationResponse(BaseModel):
       action: Literal["confirm", "reject", "edit"]
       edits: Optional[List[ItemEdit]]
   ```

   The `action` field drives the three branches in the loop. `edits` is only populated when `action == "edit"`. The literal type means LangChain's structured output will reject (and the LLM will retry) any value outside `{"confirm", "reject", "edit"}` — there is no way for the LLM to produce a fourth action and no need for the loop to handle one.

### The three branches

**`confirm`** — return `Command(goto="commit", update={"pending_confirmations": batch, "last_action": "CONFIRMED"})`. Note that `batch` is included in the state update *even though the graph already has `pending_confirmations` in state* — this is because edits may have mutated the batch in place during earlier loop iterations, and the in-state version may be stale relative to the local `batch` variable. Writing it back ensures `commit_node` reads the same batch the user actually saw and approved.

**`reject`** — build a `FAILED` `ProcessingResult` for every item in the batch (so the response node can tell the user what was *not* logged), clear `pending_confirmations`, and route to `response` instead of `commit`. Nothing is written to the DB. The user gets a "I didn't log anything" reply.

**`edit`** — call `_apply_edits` to mutate the batch in place, rebuild the preview from the updated batch, and **let the loop iterate**. The next iteration will hit `interrupt(preview)` again with the *updated* preview, and the user will see their edit reflected before deciding to confirm/reject/edit again. There's no return statement in the edit branch — control naturally flows back to the top of `while True`.

### Why the loop is the right shape

The pause-resume-pause cycle is what makes "edit" feel natural to the user. Each edit is a fresh interaction:

```
Server: [shows batch with chicken 200g, rice 150g]
User:   "change the rice to 200g"
Server: [shows batch with chicken 200g, rice 200g]
User:   "remove the chicken"
Server: [shows batch with rice 200g]
User:   "yes"
Server: [logs rice 200g, sends confirmation]
```

Each `interrupt()` call is a separate suspension. The thread is paused after each one, the user replies on their own time, the bot resumes the run, and the loop iterates. From the graph's perspective, each iteration is an *interruptible await point*; there is nothing special about being inside a loop versus being at the top level. From the user's perspective, it's just a conversation that happens to maintain state.

This is the only place in FitPal where a node legitimately pauses more than once in a single execution. Every other node runs to completion in one shot.

## Phase 3 — Dynamic Routing via `Command`

`confirmation_node` is the only node in the entire FitPal graph that returns `Command` instead of a state-update dict. The signature is explicit:

```python
async def confirmation_node(
    state: AgentState, runtime: Runtime[ContextSchema],
) -> Command[Literal["commit", "response"]]:
```

The `Literal["commit", "response"]` type parameter is enforced by LangGraph when the graph compiles. If `confirmation_node` ever returned `Command(goto="some_other_node")`, type checking and graph validation would fail at compile time, which catches typos and stale references before they hit runtime.

The graph definition reflects this. Look at [src/agents/nutritionist.py:87-89](../../src/agents/nutritionist.py#L87-L89):

```python
# confirmation → uses Command return (dynamic routing, no conditional edges needed)
# commit → response (always)
workflow.add_edge("commit", "response")
```

There are **no `add_conditional_edges` for `confirmation`** in the graph. Every other branching node in FitPal uses `add_conditional_edges` with a route function (`route_parser`, `route_after_selection`, `route_after_calculate_macros`), but `confirmation` doesn't, because the routing is encoded in the `Command` return value at runtime, not in the graph topology at compile time.

This distinction matters because it answers a question that comes up reading the graph definition: "where does `confirmation` go next?" The answer is "look at the node code, not the graph definition" — and the comment in `nutritionist.py` makes that explicit so future readers don't waste time looking for missing edges.

When to use `Command` vs `add_conditional_edges`:

- **Use `add_conditional_edges`** when the next node is decided from state that already exists when the node *finishes* — the route function reads state and picks an edge.
- **Use `Command`** when the next node depends on something the node *learned during its own execution* (an external interrupt response, an LLM tool-call decision, an exception path), and you want the routing decision to live next to the code that produced the decision instead of in a separate route function.

Confirmation is the canonical case for `Command`: the routing decision is "commit if the user said yes, otherwise respond" and that decision is computed inside the loop body. Putting it in an `add_conditional_edges` route function would require dumping the parsed `decision.action` into state and then re-reading it from a separate function, which is busywork.

## Phase 4 — The Edit Pipeline (`_apply_edits`)

The edit branch of the loop calls `_apply_edits(batch, decision.edits)`, which is where the in-place mutation happens. Two edit types are supported by the schema, and they have non-trivial semantics worth understanding.

Full implementation from [confirmation_node.py:152-196](../../src/agents/nodes/confirmation_node.py#L152-L196):

```python
async def _apply_edits(batch: list[MacroResult], edits: list) -> list[MacroResult]:
    # Process removals in reverse order to preserve indices
    remove_indices = sorted(
        [e.item_index for e in edits if e.edit_type == "remove"],
        reverse=True,
    )
    for idx in remove_indices:
        if 0 <= idx < len(batch):
            batch.pop(idx)

    # Process amount changes
    for edit in edits:
        if edit.edit_type == "change_amount" and edit.new_amount_g is not None:
            if 0 <= edit.item_index < len(batch):
                item = batch[edit.item_index]
                old_amount = item["amount_g"]
                new_amount = edit.new_amount_g

                if item["food_id"] is not None:
                    # DB item — recalculate via tool
                    macros = await calculate_food_macros.ainvoke(
                        {"food_id": item["food_id"], "amount_g": new_amount}
                    )
                    if "error" not in macros:
                        item["amount_g"] = new_amount
                        item["calories"] = macros["calories"]
                        item["protein"] = macros["protein"]
                        item["carbs"] = macros["carbs"]
                        item["fat"] = macros["fat"]
                else:
                    # Estimated item — scale proportionally
                    if old_amount > 0:
                        ratio = new_amount / old_amount
                        item["amount_g"] = new_amount
                        item["calories"] = round(item["calories"] * ratio, 1)
                        item["protein"] = round(item["protein"] * ratio, 1)
                        item["carbs"] = round(item["carbs"] * ratio, 1)
                        item["fat"] = round(item["fat"] * ratio, 1)

    return batch
```

Three things in this function are non-obvious and worth documenting because they're the kind of thing a future contributor would otherwise have to rediscover by breaking it.

### Removals are processed in reverse index order

If the user says "remove items 0 and 2", the naive implementation would be:

```python
for idx in [0, 2]:
    batch.pop(idx)
```

This is wrong. After `batch.pop(0)`, the item that was at index 2 is now at index 1, but the loop still pops index 2 next — which hits whatever was at index 3 in the original batch. A multi-removal corrupts arbitrary other items.

The fix is to process removals in **reverse index order**:

```python
remove_indices = sorted([...], reverse=True)
for idx in remove_indices:
    batch.pop(idx)
```

Popping the highest index first means lower indices are unaffected — the item at index 0 stays at index 0 regardless of what happens to index 2. Indices remain stable for the remainder of the loop.

This is a small but real footgun. If you ever change the edit pipeline, **preserve this ordering**, or replace it with a different correct approach (e.g. mark items as deleted via a sentinel and filter at the end). Don't iterate forward over `remove_indices`.

### DB items recalculate via the tool; estimated items scale proportionally

When the user changes an item's amount, the new macros come from one of two completely different sources depending on whether the item is backed by a DB row.

**DB items (`food_id is not None`):** The function calls `calculate_food_macros.ainvoke({"food_id": ..., "amount_g": new_amount})`. The tool reads the per-100g values from the `food_items` row, multiplies by the new amount, and returns authoritative macros. This is the same path `calculate_macros_node` uses for the initial calculation — we just re-run it with the new amount. The result is exactly as accurate as the original.

**Estimated items (`food_id is None`):** There is no DB row to query. The original macros came from the LLM, and we have no way to ask the LLM to "recalculate" without running another estimation pass (which would be slow and would also produce a slightly different answer due to LLM nondeterminism). Instead, the function scales the existing macros by the ratio of new to old amount:

```python
ratio = new_amount / old_amount
item["calories"] = round(item["calories"] * ratio, 1)
# ... and so on for protein, carbs, fat
```

This assumes the macro density is linear in mass — which is approximately true for most foods ("more rice is proportionally more calories"), and badly false for some ("more cooking oil added to the pan" doesn't scale the same way as "the dish is twice as big"). The approximation is good enough for the edit case because:
- The user already accepted the per-100g implicit assumption when they accepted the original estimate.
- The alternative (re-running the LLM) is slower, more expensive, and not noticeably more accurate.
- If the user wants a fundamentally different food, they should reject and re-enter, not edit the amount.

The `if old_amount > 0:` guard prevents a divide-by-zero. If `old_amount` is somehow zero (which shouldn't happen because `calculate_macros_node` rejects zero-amount items earlier), the edit silently no-ops. This is a defensive safeguard, not a normal path.

### Edits never call `interrupt()` themselves

`_apply_edits` is pure mutation — it has no `interrupt()` calls of its own. The function returns the mutated batch, control flows back into `confirmation_node`, the loop iterates, the *next* iteration hits `interrupt(preview)`, and *that's* where the graph pauses again. The edit pipeline and the interrupt pipeline are cleanly separated: edits mutate state, interrupts pause execution, and they happen at different points in the loop body.

This separation is what makes "edit then edit again then confirm" trivial to implement. Each edit is one function call; each user interaction is one interrupt; the loop glues them together. There's no special "edit mode" the node has to enter and exit, no flag to track, no state machine — just a `while True` that runs until the user says yes or no.

## HITL Relay over Telegram (Brief)

The full bot plumbing is documented in [bot-gateway.md](bot-gateway.md), but the contract between the graph and the bot is small enough to capture here so the HITL pattern is self-contained.

When the graph hits `interrupt(preview)`, the run is suspended and `preview` becomes available on the thread state under the pending tasks' `interrupts` field. The bot is responsible for noticing this and surfacing it to the user. From [bot/gateway.py:120-148](../../bot/gateway.py#L120-L148):

```python
async def _get_interrupt_state(thread_id: str) -> tuple[bool, str | None]:
    """Check if the graph is paused at an interrupt and extract the interrupt value."""
    # ... fetch thread state from langgraph SDK ...
    interrupts = tasks[0].get("interrupts", [])
    if not interrupts:
        return False, None
    value = interrupts[0].get("value")
    if value:
        return True, _format_interrupt_value(value)
```

The bot then sends the formatted text to Telegram. The user replies in the chat. The bot detects that the session is in an `interrupted` state and calls the run with `command={"resume": message.text}` instead of starting a new run:

```python
if session.get("interrupted"):
    await client.runs.create(
        thread_id=thread_id,
        ...,
        command={"resume": message.text},
    )
```

The `resume` value is exactly what `interrupt(preview)` returns inside `confirmation_node`. From the node's perspective, `interrupt()` is a normal function call that "returns the user's text" — the entire pause/resume machinery is invisible to the node.

Three contracts hold this together:

1. **The graph emits structured data, not user-facing strings.** `_format_batch_preview` returns a dict with `question`, `items`, `totals`. The bot is responsible for rendering that dict into a Telegram message. The graph never knows about Telegram's markdown, button limits, or message length caps.

2. **The bot polls thread state to detect interrupts.** It doesn't subscribe to events or maintain a websocket — it checks the thread state after each run completes. If the state shows pending interrupts, the next user message resumes; if not, the next user message starts a new run.

3. **The resume value is just a string.** Whatever the user types becomes the return value of `interrupt()`. The graph parses it via the LLM (`_parse_confirmation`) — no structured input from the bot, no JSON, no special protocol. This keeps the bot dumb and the graph smart, which is the right boundary for a system where the LLM is the natural-language layer.

This contract was the source of an early bug (echoed in the project memory at 2026-03-25): the bot was sending the user's *previous message* back instead of the interrupt prompt, because it wasn't reading the interrupt value from the thread state correctly. The fix was the `_get_interrupt_state` extraction shown above. The lesson is that the bot has to actively read the interrupt value out of pending tasks — there's no callback or push mechanism.

## Testing the HITL Flow

The full pattern lives in the test-engineering skill ([.claude/skills/test-engineering/references/graph-api-testing.md](../skills/test-engineering/references/graph-api-testing.md)), but the shape is:

1. **Turn 1**: Send the initial user message via `client.runs.wait(...)`. Assert the run is paused with `_assert_interrupted()` (a helper that checks the thread state for pending interrupts).
2. **Turn 2**: Resume the run with `command={"resume": "<user reply>"}`. Assert the final state is what you expect (committed, rejected, or back at another interrupt for an edit case).

Multi-edit flows are just multiple turn-2's: each `resume` call returns the user to the next interrupt or to the final state. The test infrastructure doesn't need to know anything special about loops.

## Cross-References

- **[llm-config.md](llm-config.md)** — `confirmation_node` uses the standard structured-output pattern via `get_llm_for_node("confirmation_node")` and `.with_structured_output(ConfirmationResponse)`. The temperature override for this node lives in `NODE_CONFIGS`. The prompt is loaded at module import time per the prompt-loading rule.
- **[off-menu-estimation.md](off-menu-estimation.md)** — explains where `source="estimated"` items come from (`calculate_macros_node` LLM path) and how `commit_node` persists them as new `food_items` rows with back-calculated per-100g values. The HITL flow only needs to know that estimated items exist and look different in the preview; it doesn't need to know how they were produced.
- **[state-schemas.md](state-schemas.md)** — covers `MacroResult` and `pending_confirmations` in the broader context of `AgentState`, plus the InputState/OutputState split that hides `pending_confirmations` from external callers.
- **[data-flow.md](data-flow.md)** — covers the multi-item loop (`food_search` → `agent_selection` → `calculate_macros` → loop back) that produces the batch in the first place.
- **[bot-gateway.md](bot-gateway.md)** — full aiogram plumbing for the interrupt relay, session lifecycle, and the resume protocol.
- **[tool-first.md](tool-first.md)** — `commit_node` uses `log_food_entry`, `create_food_item`, and `query_food_logs` tools. `_apply_edits` uses `calculate_food_macros` for DB-item recalculation.

## Rules

Hard rules. Violating any of these is a bug.

1. **`interrupt()` is only called from `confirmation_node`.** Grep `src/agents/nodes/` for `interrupt(` — the result must contain only `confirmation_node.py`. If a future node needs HITL, it should follow the same pattern (loop, structured-output parsing, `Command` return), not introduce a second style.

2. **`confirmation_node` always returns `Command`, never a plain dict.** The signature `-> Command[Literal["commit", "response"]]` is enforced by the type checker; respect it. If you need to add a new exit route, add it to the literal type *and* to the `Command(goto=...)` return value, not by switching to a dict.

3. **No DB writes happen between `calculate_macros_node` and `commit_node`.** The batch lives entirely in `pending_confirmations` (a state field, checkpointed but not persisted to application tables). `_apply_edits` mutates the in-memory list. `commit_node` is the *only* node that creates `DailyLog` rows (and `food_items` rows for estimated items). Reject and edit-loops never persist anything.

4. **`pending_confirmations` is cleared at every legitimate exit.** `confirmation_node` clears it on reject (`"pending_confirmations": []`). `commit_node` clears it after successful writes. The only state where `pending_confirmations` is non-empty is "between accumulation and confirmation/commit". Do not leave items in this field after the HITL flow ends — downstream nodes assume an empty list means "nothing to confirm".

5. **The interrupt loop is the only legal pattern for "multiple pauses in one node execution".** Every other node in FitPal runs to completion in one shot. If you find yourself wanting to call `interrupt()` from a node that isn't `confirmation_node`, reconsider — you're probably better off splitting the work into multiple nodes connected by graph edges.

6. **When extending `ItemEdit`, update the schema, the prompt template, and `_apply_edits` together.** The schema (`src/schemas/confirmation_schema.py`), the system prompt (`prompts/confirmation_parser.md`), and the dispatcher (`_apply_edits` in `confirmation_node.py`) form a single contract. Changing one without the others either makes the LLM produce invalid output (schema rejects), or makes the dispatcher silently ignore valid edits (no branch handles the new type).

7. **Removals iterate in reverse index order.** Forward iteration corrupts indices for multi-removal. If you change the removal logic, preserve this property or replace it with an equivalently correct approach (e.g. sentinel-mark and filter).

8. **DB items recalculate via the tool; estimated items scale proportionally.** Don't unify the two paths. The `food_id is not None` check is the operational signal — use it, don't try to infer from `source` or other fields.

9. **`confirmation_node` has no conditional edges in the graph definition.** Routing is in the `Command` return value. The comment in `nutritionist.py` (`# confirmation → uses Command return ...`) makes this explicit — preserve it. Do not add `add_conditional_edges` for `confirmation` "for consistency with other nodes"; that would create two competing routing mechanisms.

10. **The graph emits structured interrupt payloads, not user-facing strings.** `_format_batch_preview` returns a dict. Rendering to Telegram (or any other UI) is the bot's job. Do not put markdown or user-language formatting inside the graph — that breaks the provider-agnostic contract and makes the graph harder to test.
