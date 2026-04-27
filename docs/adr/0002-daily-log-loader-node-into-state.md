# ADR-0002: `daily_log_today` lives in AgentState via a loader node, not in ContextSchema

- **Status**: Accepted 2026-04-25
- **Area**: data, agent-architecture
- **Deciders**: Dolev (with Claude Opus 4.7)

## Context

The 2026-04-17 daily-log injection design (`docs/plans/daily-log-injection-and-israel-tz-serialization.md`) placed `daily_log_today` on `ContextSchema`, fetched per-message by `bot/gateway.py` and read once by `response_node`. The pattern was modeled on PR #21 (`nutrition_plan` injection) for consistency. Per-message freshness was considered sufficient and was wired into both the new-input and HITL-resume paths.

On 2026-04-25, audit of thread `73ed31fb-8391-4c97-a05f-a4b672c6fcd5` revealed the model fails: a HITL-resume turn caused `commit_node` to write 4 new food rows to the DB, but `response_node` (running later in the same request) reported "4 protein / 2 carb portions" instead of the correct "5.6 / 5". DB inspection confirmed all 9 rows for the day. Cause: `runtime.context` is request-scoped and immutable from inside the graph. The gateway captured the snapshot *before* the request, the graph mutated DB *during* the request, and the snapshot consumed by `response_node` was never refreshed.

Two compounding factors pushed the decision beyond a quick patch:

1. **Future consumers are likely** — a coaching/recommendation node, an end-of-day summary node, and possibly `calculate_macros_node` for plan-aware estimation will all want `daily_log_today`. Per-consumer self-fetching means N queries per turn and risks divergence between fetches inside the same request.
2. **Mutability is graph-internal, not ambient.** `daily_log_today` is the only context field that gets stale during a request because `commit_node` is the only node that mutates its source. `user_id` and `user_profile` are stable for the request's duration; `daily_log_today` is not.

A naive "move to state" was considered and complicated by the fact that LangGraph state persists across turns within a thread (via the checkpointer), creating a *different* staleness risk if not actively refreshed.

## Decision

`daily_log_today` is removed from `ContextSchema` and added to `AgentState` as a `list[dict]` field. A new `load_daily_context` node fetches it via `get_todays_logs_serialized(session, user_id)` and writes it to state. The node runs at graph entry (before any consumer) and again after `commit_node` (so post-commit consumers see fresh data). Cross-turn state persistence is harmless because the entry-edge run guarantees the field is overwritten on every turn. The gateway stops fetching the daily log; its responsibility shrinks to identity (`user_id`) and `user_profile`.

## Alternatives considered

**A. Keep `daily_log_today` in `ContextSchema` (status quo).** Rejected because `runtime.context` is immutable from inside the graph and request-scoped. The gateway snapshot is taken before `commit_node` runs, so any consumer downstream of `commit_node` in the same request sees stale data — the exact failure observed in thread `73ed31fb-…`. No in-graph fix is possible without leaving this layer.

**B. Per-node self-fetch — each consumer (e.g. `response_node`) calls `get_todays_logs_serialized` directly when it runs.** Rejected because future consumers are anticipated (coaching node, summary node, plan-aware estimation in `calculate_macros_node`); N consumers in the same turn would mean N independent DB queries with possible divergence between fetches. Acceptable only while there is exactly one consumer.

**C. Move to `AgentState` without a loader node — write `daily_log_today` from inside `commit_node` and rely on the gateway snapshot otherwise.** Rejected because it splits ownership: the gateway populates state for non-commit turns, `commit_node` populates state for commit turns. Two writers, one field, easy to drift. Also makes future "non-commit nodes that need fresh data" awkward.

## Consequences

**What this makes easier**

- Any future node that needs today's log (coaching, summary, plan-aware estimation) reads `state["daily_log_today"]` with no new fetches and no new wiring.
- Post-commit freshness is automatic: `response_node` and any other downstream consumer always see the rows `commit_node` just wrote.
- Gateway responsibility shrinks to identity and stable per-user data; the bot stops being the freshness authority for graph-internal data.
- The freshness contract is a single graph-level rule ("loader runs at entry and after commit") instead of an implicit assumption about request timing.

**What this makes harder**

- One extra DB query per commit turn (entry + post-commit refresh). Indexed on `user_id` + day; cost is negligible at current scale.
- The "ContextSchema for per-user X" pattern from PR #21 no longer applies uniformly — `user_profile` stays in context, `daily_log_today` moves to state. Future "per-user X" decisions need to ask: *is this mutable mid-graph?*
- Two new graph edges (entry → loader, commit → loader → response). Graph topology is slightly more complex.
- Tests that previously asserted `daily_log_today` lives in context (per `tests/conftest.py` comment) need to be updated.

**What we are committing to**

- `daily_log_today` is graph-internal mutable data, not ambient request context. State, not context, is its home.
- The loader node is the single source of truth for fetching today's log into the graph. Nodes do not self-fetch this field.
- The loader runs at every turn entry; this is the mechanism that makes cross-turn state persistence harmless. Any future graph refactor that bypasses entry-loader execution must explicitly preserve this guarantee.
- The gateway's role is identity + stable per-user data only; mutable per-day data is the graph's responsibility.
- The "loader after mutation" rule generalizes: any future node that mutates data the loader reads (e.g., a HITL daily-stats confirm-and-commit flow, a delete-log-entry flow) must add a refresh edge into the loader before any consumer node runs in the same request. The loader is the only mechanism for refreshing this state mid-graph.

## Revisit trigger

Revisit when manually maintaining loader edges becomes a hazard — concretely, when adding a new mutation node requires updating the graph in a way that's easy to forget. Likely signals: 3+ DB-mutating nodes, or the introduction of parallel branches where a mutation and a consumer can run in different branches. At that point, evaluate whether to automate the refresh (middleware, request-scoped cache) — the underlying model (state-owned, loader-controlled freshness) does not change.

## Related

- `docs/plans/daily-log-injection-and-israel-tz-serialization.md` — the original 2026-04-17 plan that placed `daily_log_today` on `ContextSchema`. This ADR supersedes its "context-only, not state" assumption.
- `commit_logs/2026-04-17_11-54-54_feat-daily-log-injection-and-israel-tz.md` — implementation record for the original design.
- `docs/patterns/runtime-context.md` — the runtime-context pattern this ADR partially carves out (`user_id`, `user_profile` remain; `daily_log_today` does not).
- `src/context.py` — `ContextSchema` definition (will lose the `daily_log_today` field).
- `src/agents/state.py` — `AgentState` (will gain the `daily_log_today` field).
- `src/agents/nodes/response_node.py` — current consumer (will read from state instead of context).
- `src/agents/nodes/commit_node.py` — current mutator (will gain a refresh edge to the loader).
- `bot/gateway.py` — current fetcher (`_load_todays_log` will be removed; `daily_log_today` no longer in the HTTP context body).
- `src/services/daily_log_service.py` — `get_todays_logs_serialized` (the fetcher itself stays; just gets a new caller).
- LangSmith thread `73ed31fb-8391-4c97-a05f-a4b672c6fcd5` (2026-04-22) — the audit conversation that surfaced the staleness bug.
- ADR-0001 — adjacent decision on app-layer authorization (no direct dependency, but same area: graph-side data ownership).
