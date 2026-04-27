# ADR-0003: `daily_log_today` loader sits only before `response_node`, not at graph entry

- **Status**: Accepted 2026-04-26
- **Area**: data, agent-architecture
- **Deciders**: Dolev (with Claude Opus 4.7)

> **Supersedes**: [ADR-0002](0002-daily-log-loader-node-into-state.md). Same problem, simpler topology. ADR-0002's *Context*, *Alternatives considered*, and *Revisit trigger* sections still hold and are not restated in full here.

## Context

ADR-0002 established that `daily_log_today` belongs in `AgentState`, populated by an explicit loader node (`load_daily_context`) — not in `ContextSchema`, where it could not be refreshed mid-graph after `commit_node` writes new rows. That decision is unchanged.

ADR-0002's Decision section also specified the loader's *position*: at graph entry **and again** after `commit_node`, with a conditional edge dispatching to `input_parser` or `response` based on `state.last_action`. The motivation was forward-compatibility for hypothetical mid-graph consumers (a coaching node, plan-aware estimation in `calculate_macros_node`, an end-of-day summary node).

While planning the implementation, the question was raised: *if today the only consumer of `daily_log_today` is `response_node`, why pre-pay the topology cost for hypothetical consumers?* When a real mid-graph consumer arrives, adding a loader edge for *that consumer* is the same single-edge change either way — the entry-point design does not actually save future work, it only front-loads it onto present-day complexity for cases that may never materialize.

A grep confirmed: `response_node` is the only reader of `daily_log_today` in the current codebase. The forward-compat argument is real but speculative.

## Decision

`daily_log_today` still lives in `AgentState`, still populated by the `load_daily_context` node. **The loader's position changes**: instead of running at graph entry plus a refresh after commit, it runs as the **single hop between any node and `response_node`**. Every former path that ended in `response` is rewired to go through `load_daily_context` first. The graph entry point is unchanged (`input_parser`).

The freshness invariant becomes a single graph-level rule: *nothing reaches `response` without passing through `load_daily_context` first*.

## Alternatives considered

**A. Keep ADR-0002's entry + post-commit topology.** Rejected because it pre-pays topology cost for consumers that do not exist. The "future-proofing" benefit only materializes if mid-graph consumers actually arrive, and even then the cost of adding an edge for the new consumer is the same regardless of where the loader currently sits.

**B. Per-node self-fetch in `response_node` (no loader node, no state field).** Rejected for the same reasons given in ADR-0002 alternative B: when a second consumer arrives, it duplicates the fetch and risks divergence between fetches inside the same request. A graph-level node is still the right home; this ADR only changes *where* the node sits.

**C. The current ADR-0003 design (loader only before `response_node`).** Chosen. Simpler graph topology — no entry-point change, no conditional edge from the loader, no state-driven branching. Same forward-extension cost as ADR-0002 (one edge per new consumer at the time it actually exists).

## Consequences

**What this makes easier**

- Graph topology is structurally simpler: no entry-point shift, no conditional edge from the loader, no branching based on `last_action`. The freshness rule is one sentence: every path to `response` goes through the loader.
- Every consumer of `daily_log_today` reads from `state["daily_log_today"]`; the loader writes it; nothing else writes it. Single producer, single rule.
- No more "did I remember to add the refresh edge after this mutator?" question for the *current* mutator set — the rule is enforced at the consumer's gate, not after each mutation.

**What this makes harder**

- One extra DB query per CHITCHAT-style turn that goes `input_parser → load_daily_context → response` even though no mutation happened. Cost: ~5ms, indexed query. Acceptable.
- A future mid-graph consumer (e.g. a coaching node that runs *before* `response_node`) cannot read `state["daily_log_today"]` without an additional loader edge being wired in for it. ADR-0002's design would have given that consumer the data for free. This is the deferred cost we explicitly accept.
- The "loader after mutation" rule from ADR-0002's Consequences section is *replaced* by the simpler "loader before response" rule. Future contributors must understand the two are not equivalent.

**What we are committing to**

- `daily_log_today` is graph-internal mutable data, not ambient request context. State, not context, is its home. (Unchanged from ADR-0002.)
- The loader is the single source of truth for fetching today's log into the graph. Nodes do not self-fetch this field. (Unchanged from ADR-0002.)
- The freshness invariant is now: **every path that reaches `response_node` passes through `load_daily_context` first**. Graph topology must preserve this on every refactor. Any new edge into `response` that bypasses the loader is a bug.
- When a future consumer of `daily_log_today` is added that runs *before* `response_node`, it must either (a) be wired with its own loader edge before it, or (b) trigger a re-evaluation of the topology back toward ADR-0002's entry-loader design. This is the explicit deferred cost.

## Revisit trigger

ADR-0002's revisit trigger still applies: revisit when manually maintaining loader edges becomes a hazard — concretely, when adding a new mutation node or consumer requires updating the graph in a way that's easy to forget. This ADR adds one more concrete signal: **the first time a consumer of `daily_log_today` is added that runs before `response_node`** — at that moment, weigh wiring an additional loader edge against returning to the entry-loader design from ADR-0002.

## Related

- [ADR-0002](0002-daily-log-loader-node-into-state.md) — superseded by this ADR. Same Context, Alternatives (A–C), and Revisit trigger reasoning still apply; only the *Decision* topology specifics differ.
- `docs/plans/daily-log-loader-before-response.md` — the implementation plan for this ADR.
- `docs/plans/daily-log-loader-node-into-state.md` — the prior implementation plan (entry + post-commit topology). Historical only; superseded.
- `docs/patterns/runtime-context.md` — pattern doc describing the rule for what belongs in `ContextSchema` vs `AgentState`. Unchanged by this ADR.
- `src/agents/nutritionist.py` — graph wiring; the topology change lives here.
- `src/agents/nodes/load_daily_context_node.py` — the loader node.
- `src/agents/nodes/response_node.py` — the only current reader of `state["daily_log_today"]`.
- LangSmith thread `73ed31fb-8391-4c97-a05f-a4b672c6fcd5` (2026-04-22) — the audit conversation that surfaced the staleness bug both ADRs address.
