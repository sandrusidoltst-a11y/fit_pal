# Architecture Decision Records (ADRs)

This folder is the **persistent log of architectural decisions** for FitPal. One entry per decision. Each entry links to a detail file and, when useful, to the conversation or planning note that produced it.

## How to use this folder

- **Scanning** — read this index. Every decision is one row with its current status, so you can see "what's in force" at a glance.
- **Revisiting** — click through to the detail file. Detail files are written at decision time and do not change after acceptance.
- **Changing a past decision** — write a *new* ADR that supersedes the old one. Do not edit old detail files. Update the index row's status to `Superseded by ADR-NNNN`.

## Index vs detail

- **This file (`README.md`)** — mutable. Status, dates, and links are updated as things evolve.
- **Detail files (`NNNN-slug.md`)** — immutable once accepted. If decisions change, supersede them; do not rewrite them.

This split keeps the scannable surface current and preserves history intact.

## Entry template

```markdown
## ADR-NNNN: Title

- **Status**: Proposed | Accepted (YYYY-MM-DD) | Superseded by ADR-NNNN | Deprecated
- **Area**: auth, data, deploy, testing, ux, cost, …
- **One-liner**: The decision in one sentence.
- **Trade-off**: What we accepted in exchange.
- **Detail**: [full record](NNNN-slug.md)
- **Conversation**: [[brain/conversations_beckups/YYYY-MM-DD_slug]] (optional)
- **Related**: links to tasks, PRs, other ADRs
```

## Detail file template

```markdown
# ADR-NNNN: Title

- **Status**: Accepted YYYY-MM-DD
- **Area**: …
- **Deciders**: Dolev (and optional LLM assistant credit)

## Context

The situation and constraints that forced the decision. What made this a real choice, not an obvious one?

## Decision

What we chose, stated directly. No hedging.

## Alternatives considered

Each alternative with *why* it was rejected. At minimum the serious ones — not every hypothetical.

## Consequences

What this makes easier. What it makes harder. What we are committing to.

## Revisit trigger

The condition that should make us reopen this decision. "When X happens, re-evaluate."

## Related

Tasks, PRs, plan docs, other ADRs.
```

---

## Decisions

### ADR-0001: App-layer user authorization via `user_id` scoping

- **Status**: Accepted (2026-04-25) · revisit post-POC
- **Area**: auth, security
- **One-liner**: User data isolation is enforced by Python `WHERE user_id = ?` filters in the service layer, not by Postgres Row-Level Security. The bot holds a superuser DB connection (`SUPABASE_DB_URL`) and the Supabase service-role key.
- **Trade-off**: Simple now, refactor later (3–5 days) if scale or multi-tenant isolation demands DB-layer enforcement. Bot compromise currently equals full DB compromise.
- **Detail**: [full record](0001-app-layer-user-authorization.md)
- **Conversation**: [[brain/conversations_beckups/2026-04-25_service-role-key-and-auth-architecture]] *(to be backed up)*
- **Related**: TASKS.md → *Security audit of onboarding*; `docs/plans/phase3-auth-rls-telegram-gateway.md`; `bot/supabase_admin.py`; `src/database.py`

### ADR-0002: `daily_log_today` lives in AgentState via a loader node, not in ContextSchema

- **Status**: Superseded by ADR-0003 (2026-04-26)
- **Area**: data, agent-architecture
- **One-liner**: `daily_log_today` moves from `ContextSchema` to `AgentState`, populated by a loader node that runs at graph entry and after any DB-mutating node, replacing the gateway-injected per-request snapshot.
- **Trade-off**: One extra DB query per commit turn and manual refresh-edge wiring per new mutator, in exchange for guaranteed mid-graph freshness and a single forward-compatible model for multi-consumer growth.
- **Detail**: [full record](0002-daily-log-loader-node-into-state.md)
- **Conversation**: [[brain/conversations_beckups/2026-04-25_daily-log-loader-node-into-state]] *(to be backed up)*
- **Related**: `docs/plans/daily-log-injection-and-israel-tz-serialization.md` (superseded assumption); `docs/patterns/runtime-context.md`; `src/context.py`; `src/agents/state.py`; `src/agents/nodes/response_node.py`; `src/agents/nodes/commit_node.py`; `bot/gateway.py`; LangSmith thread `73ed31fb-8391-4c97-a05f-a4b672c6fcd5`; ADR-0001

### ADR-0003: `daily_log_today` loader sits only before `response_node`, not at graph entry

- **Status**: Accepted (2026-04-26) · revisit when first non-`response_node` consumer of `daily_log_today` is added, or when manual loader-edge maintenance becomes a hazard
- **Area**: data, agent-architecture
- **One-liner**: Supersedes ADR-0002's loader topology — the `load_daily_context` node sits as the single hop before `response_node` (every former path to `response` is rewired through it), instead of running at graph entry plus a refresh after commit.
- **Trade-off**: Simpler graph topology and one DB query per CHITCHAT turn now, in exchange for deferring forward-compat for hypothetical mid-graph consumers (each future non-`response_node` consumer must wire its own loader edge).
- **Detail**: [full record](0003-daily-log-loader-before-response.md)
- **Conversation**: [[brain/conversations_beckups/2026-04-25_daily-log-loader-node-into-state]] *(to be backed up — same conversation as ADR-0002)*
- **Related**: ADR-0002 (superseded); `docs/plans/daily-log-loader-before-response.md`; `docs/patterns/runtime-context.md`; `src/agents/nutritionist.py`; `src/agents/nodes/load_daily_context_node.py`; `src/agents/nodes/response_node.py`; LangSmith thread `73ed31fb-8391-4c97-a05f-a4b672c6fcd5`

### ADR-0004: Schema-to-state translation owned by the structured-output node

- **Status**: Accepted (2026-05-06) · revisit on drift incident or when a second node starts producing the same schema
- **Area**: state, llm
- **One-liner**: The node that calls `with_structured_output(SomeSchema)` is the sole translator from that schema into LangGraph state; Pydantic models live at the LLM I/O boundary and `TypedDict` sub-states live in `AgentState`, with no central translator helper.
- **Trade-off**: Apparent duplication between schema variants and sub-state TypedDicts (2-3 fields per pair) and discipline-only drift prevention, in exchange for friction-free LangGraph checkpointing, plain-dict reader semantics across the graph, and independent evolution of the schema and state layers.
- **Detail**: [full record](0004-schema-to-state-translation-ownership.md)
- **Conversation**: [[brain/conversations_beckups/2026-05-06_schema-to-state-translation-ownership]] *(to be backed up)*
- **Related**: `docs/plans/discriminated-action-state-refactor.md`; `docs/patterns/state-schemas.md`; `docs/patterns/llm-config.md`; `src/schemas/input_schema.py`; `src/agents/state.py`; `src/agents/nodes/input_node.py`; `src/agents/nodes/personal_stats_node.py`

### ADR-0005: Split `last_action` into `user_intent` + `pipeline_stage`

- **Status**: Accepted (2026-05-11) · revisit if `pipeline_stage` value set grows past ~10 or a drift incident ships
- **Area**: state, routing
- **One-liner**: `AgentState.last_action` is split into `user_intent` (set once by parser, immutable per turn) and `pipeline_stage` (overwritten freely by intermediate nodes); `last_action`, `GraphAction`, and the legacy-fallback helpers were removed in the same PR after review-time validation showed the back-compat layer never fires in practice. Closes the QUERY_FOOD_INFO silent-commit risk in the same PR.
- **Trade-off**: A one-time minimal-context render for HITL threads paused across the deploy (the food still commits; only the response polish is affected), in exchange for a clean discriminator that survives the full pipeline, an explicit routing fix for QUERY_FOOD_INFO, and no deprecation tail to clean up later.
- **Detail**: [full record](0005-split-user-intent-from-pipeline-stage.md)
- **Conversation**: [[brain/conversations_beckups/2026-05-11_split-user-intent-from-pipeline-stage]] *(to be backed up)*
- **Related**: ADR-0004 (substate pattern this extends); `docs/plans/split-user-intent-from-pipeline-stage.md`; `brain/planning/query-food-info-routing-latent-bug.md`; `src/agents/state.py`; `src/agents/nutritionist.py`; `src/agents/nodes/input_node.py`; `src/agents/nodes/response_node.py`; `prompts/response_generator.md`; `tests/unit/test_intent_stage_invariants.py`; `tests/graph_api/test_graph_flows.py`
