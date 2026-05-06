# ADR-0004: Schema-to-state translation owned by the structured-output node

- **Status**: Accepted 2026-05-06
- **Area**: state, llm
- **Deciders**: Dolev (with Claude Opus 4.7)

## Context

The graph parses every user message through a structured-output LLM call (`input_parser_node` → `with_structured_output(UserIntent)`), validates the JSON output via Pydantic, then writes the relevant pieces into LangGraph state for downstream nodes to consume. As more nodes adopt the same pattern (`personal_stats_node` uses `with_structured_output(PersonalStatExtraction)`, `calculate_macros_node` uses `MacroEstimation`, `confirmation_node` uses `ConfirmationResponse`), a recurring question surfaces: should the Pydantic schemas be stored directly in state, or should state hold a separate dict shape, requiring per-node translation?

The discriminated-action-state refactor (`refactor/discriminated-action-state` branch) made the question concrete by introducing `LogFoodSubState` and `QueryStatsSubState` TypedDicts that mirror — but don't fully duplicate — the fields of their corresponding Pydantic variants (`LogFoodEvent`, `QueryStatsEvent`). The mirror is small (2-3 fields per sub-state), and the fields are renamed/dropped at the boundary (the variants carry `action` discriminators and validators that don't belong in state). A reviewer is likely to flag this as duplication; without a recorded decision, the next refactor will re-litigate the choice.

LangGraph state has constraints that make schema-direct storage non-trivial: state is checkpointed to JSON, plain `TypedDict`s round-trip cleanly while Pydantic models add `model_dump`/`model_validate` friction at every checkpoint boundary. Reader nodes also prefer dict access (`state["log_food"].get("consumed_at")`) over importing schema classes and doing isinstance dispatch.

## Decision

The node that calls `with_structured_output(SomeSchema)` is the sole translator from that schema into LangGraph state. Pydantic models live at the LLM I/O boundary; LangGraph state holds plain `TypedDict` slots populated by the translating node. Other nodes consume state via dict access only and do not import schema classes.

The apparent duplication between schema fields (`LogFoodEvent.consumed_at`, `meal_type`) and state fields (`LogFoodSubState.consumed_at`, `meal_type`) is a deliberate two-layer boundary, not redundancy: each layer has different consumers (Pydantic validator + OpenAI JSON Schema vs. LangGraph state-merge + checkpoint serialization) and the field sets overlap only partially (state drops the schema's `action` discriminator, validators, and any boundary-only fields).

## Alternatives considered

### A. Store Pydantic models directly in state (`state["log_food"]: LogFoodEvent`)

Single source of truth — no field duplication, schema validation is inherent to state reads.

**Rejected because**: LangGraph checkpoints state to JSON; Pydantic models require `model_dump`/`model_validate` round-trips at every checkpoint boundary, adding friction. Every reader node would have to import schema classes and use attribute access (`state["log_food"].consumed_at`) plus isinstance dispatch when narrowing union types. The schema's discriminator (`action: Literal[...]`) and `model_validator` get carried into state where they're redundant — `last_action` already tracks the action, and validation has already happened at the LLM boundary. State would become coupled to schema imports across the entire graph.

### B. Generate the TypedDict programmatically from the schema

Use `get_type_hints(LogFoodEvent)` minus excluded fields to define `LogFoodSubState` automatically — eliminates the manual mirror.

**Rejected because**: Python's `TypedDict` syntax requires class-block declarations; programmatic generation is awkward and breaks IDE autocomplete + mypy inference. The mirror is 2-3 fields per sub-state, lives in one file (`state.py`), and the cost of keeping it in sync is small. Automation here trades clarity for cleverness.

### C. Drop the TypedDict, use plain `dict` in state with `model_dump()` at write time

Translation still happens once, but state slots are typed as bare `dict` — no mirror to maintain.

**Rejected because**: loses IDE autocomplete and mypy on the state side. Readers lose the contract — `state["log_food"]` could carry anything and the type system wouldn't catch a typo'd key. The current TypedDict mirror gives consumers a clear, inspectable shape with one extra short class definition.

## Consequences

### What this makes easier

- **Reader nodes are simple.** `commit_node`, `stats_node`, `response_node` all read state via plain dict access (`state["log_food"].get("consumed_at")`) without importing schema classes or unwrapping Pydantic models. No isinstance dispatches, no `.model_dump()` calls in readers.
- **LangGraph checkpointing is friction-free.** State is plain dicts → JSON round-trips work natively. Adding new sub-states doesn't introduce serialization edge cases.
- **Each layer evolves independently.** Schema changes (e.g., adding a field to `LogFoodEvent` for better LLM extraction) don't force state migrations unless that field needs to persist. State-shape changes (e.g., adding a HITL bookkeeping field to `LogFoodSubState`) don't force a schema regeneration.
- **The translation point is obvious.** Schema-to-state mapping lives only in nodes that call `with_structured_output()`. New contributors know where to look.

### What this makes harder

- **Looks like duplication on first read.** Reviewers see `LogFoodEvent.consumed_at` and `LogFoodSubState.consumed_at` and assume it's redundant. This ADR exists partly to absorb that question once.
- **Adding a field to a sub-state is a two-touch change.** Add it to the schema variant (so the LLM can emit it), and add it to the sub-state TypedDict (so state can hold it), and update the translator. Three edits, all in two files (`input_schema.py`, `state.py`) plus the relevant node.
- **Drift is possible.** Nothing enforces that the TypedDict mirror stays in sync with its schema variant — discipline-only. Mitigated by the fact that the translator node touches both shapes and surfaces drift via test failures.

### What we are committing to

- **Translator-per-boundary as the project's pattern.** Any future node that calls `with_structured_output(...)` and needs to persist results will own its translation. No central "schema → state" helper.
- **Keeping the mirror small.** When a sub-state's field set grows past ~5 fields, or when multiple nodes need to translate from the same schema, revisit (see trigger below).
- **Naming convention**: schema variants end in `Event` (`LogFoodEvent`); their state slots are snake-case keys (`state["log_food"]`); the typed shape is `<Action>SubState` (`LogFoodSubState`). New sub-states should follow this triad.

## Revisit trigger

This decision should be reopened when either of the following occurs:

1. **A drift incident ships.** A `<Action>SubState` TypedDict and its corresponding schema variant fall out of sync and a bug reaches production (or a non-trivial test failure) because of it. Discipline-only mirror maintenance is the weakest part of this pattern; one real failure is the signal that the cost has become greater than the benefit.

2. **A second node starts producing the same schema.** If `PersonalStatExtraction` (or any other LLM schema) becomes a translation target for two or more nodes, we'd be writing the same `schema → state` mapping in multiple places. At that point, either centralize the translator helper or move toward storing the model directly in state (Option A above).

Either trigger means: revisit whether translator-per-boundary is still the right shape, or whether the codebase has grown into a different pattern.

## Related

- **Pattern docs**:
  - `docs/patterns/state-schemas.md` — `InputState` → `AgentState` → `OutputState` three-layer state pattern. Sub-states live inside `AgentState`.
  - `docs/patterns/llm-config.md` — `with_structured_output()` usage and centralized LLM config.
- **Plan**: `docs/plans/discriminated-action-state-refactor.md` — the refactor that introduced the first explicit per-action sub-states (`LogFoodSubState`, `QueryStatsSubState`) and made this pattern visible.
- **Code anchors**:
  - `src/schemas/input_schema.py` — schema layer (`LogFoodEvent`, `QueryStatsEvent`, etc.).
  - `src/agents/state.py` — state layer (`LogFoodSubState`, `QueryStatsSubState`).
  - `src/agents/nodes/input_node.py` — the translator node (the only place schema and state both appear).
  - `src/agents/nodes/personal_stats_node.py` — example of a structured-output node that does *not* translate to a sub-state (writes directly to DB instead). Future candidate if it grows a state-bound output.
- **Related ADRs**: none superseded or superseding.
