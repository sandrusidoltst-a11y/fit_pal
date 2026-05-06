# Feature: Discriminated-Action State Refactor — replace flat date fields with per-action sub-states

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files.

> **Branch**: `refactor/discriminated-action-state` (already created from `main`, currently checked out, clean tree).
>
> **Commit policy** — read carefully:
> - The implementation agent **MUST NOT commit** during execution. Leave the working tree dirty across all phases.
> - **No checkpoint commits between phases.** Phase boundaries are verification gates only.
> - When all 17 tasks are done and the final verification gate is green, **stop and return control to the user**. The user will run `/commit` manually to create the single refactor commit.
> - Do not run `git add`, `git commit`, `git push`, or open a PR. Do not amend any prior commit.
>
> **Companion docs (read first, in this order):**
> - `brain/planning/input-parser-state-nulling-by-fields-not-schema.md` — discovery doc. Explains the prod bug (LangSmith trace `019dd286`), its root cause (`input_parser_node:67-80` uses field-presence as the discriminator instead of `action`), why nulling exists at all (state persistence), and the sequencing rationale that ties this refactor to TASKS Important #8 (HITL add-item).
> - `brain/planning/state-lifecycle-audit.md` — full state-field × node lifecycle map. Tables A and B + per-node narrative + cross-cutting findings. The audit identifies five sites where field-presence is used as a discriminator instead of `action`; this refactor closes the date-field site (the bug) and `stats_node` priority chain by structure. The other three are explicit out-of-scope follow-ups.
> - `brain/planning/multi-turn-eval-design-session.md` — explicit OUT-OF-SCOPE marker for multi-turn evals. Future work, not a refactor prerequisite.
> - `brain/planning/query-food-info-routing-latent-bug.md` — separate latent bug, also out of scope (TASKS Important #14).

## Feature Description

Replace the flat `consumed_at` / `start_date` / `end_date` fields on `AgentState` with **per-action sub-states** (`log_food`, `query_stats`), backed by a **Pydantic discriminated union** at the LLM-output boundary (`FoodIntakeEvent` becomes `LogFoodEvent | QueryStatsEvent | QueryFoodInfoEvent | LogPersonalStatsEvent | ChitchatEvent`, discriminated by `action`).

The fix is one architectural move at three layers — schema, state, node logic — all aligned around `action` as the discriminator. The flat polysemous `consumed_at` field disappears: LOG_FOOD's "when I ate it" lives at `state["log_food"]["consumed_at"]`; QUERY_DAILY_STATS' single-day "the day I'm asking about" becomes a separately-named field `state["query_stats"]["target_date"]`. The two semantics that used to share one slot now have physically distinct slots.

This eliminates the prod date bug observed in LangSmith trace `019dd286` (Dolev, 2026-04-28): user wrote *"תוסיף לאתמול עוד פיתה..."*, the LLM emitted both `consumed_at = 2026-04-27T18:00:00Z` AND `start_date/end_date = 2026-04-27`, then the node's if-elif at `input_node.py:67-80` kept the range fields and **nulled `consumed_at`**, after which `commit_node` fell back to `datetime.now()` and wrote all six items with today's timestamp.

## User Story

As a **trainee**,
I want *"add to yesterday"* logs (and any past-date logs) to land on the day I said,
So that my daily summary the next morning isn't corrupted with food from a different day.

As **Dolev (the developer)**,
I want each `action`'s state to physically isolate its date semantics,
So that future features (HITL add-item, second interrupts, webhook triggers) can extend the graph without re-litigating "which fields are valid for which intent" — the schema enforces the answer.

## Problem Statement

The flat `consumed_at` / `start_date` / `end_date` fields on `AgentState` are read by three consumers (`commit_node`, `stats_node`, `response_node`) with three different semantics, and none asserts the action it expects:

- `commit_node` reads `consumed_at` as a **write timestamp** (LOG_FOOD).
- `stats_node` reads `consumed_at` as a **single-day query target** (QUERY_DAILY_STATS fallback) AND `start_date`/`end_date` as a **range query**.
- `response_node` injects all three into the LLM JSON context, gating range fields by `last_action` but injecting `consumed_at` unconditionally.

The writer (`input_parser_node:67-80`) decides which fields to keep vs. null based on **which fields the LLM happened to populate**, not on `action`:

```python
if result.start_date and result.end_date:
    keep range, null consumed_at         # branch A — fired in trace 019dd286
elif result.consumed_at:
    keep consumed_at, null range
else:
    null all three
```

When the LLM emits all three (legitimately ambiguous user input — *"add to yesterday"*), branch A wins, `consumed_at` is destroyed, and `commit_node` silently falls back to `now()`. The user's data lands on the wrong day with no error.

The single-turn `eval_input_parser_hebrew.py` does **not** consistently reproduce this bug (confirmed by experiment `input-parser-hebrew-gpt-5.4-mini-36a3dd0f`, all 35 examples have `no_query_dates_on_log_food` and `no_consumed_at_on_query` at 100%). The bug requires the LLM to emit both date shapes simultaneously, which the eval inputs don't reliably trigger. Therefore the refactor's regression contract is **not** an LLM-quality eval — it's a **mocked-LLM unit test** that forces both fields set, plus a **graph-api test** that drives a full "log to yesterday" flow end-to-end.

## Solution Statement

The refactor is one architectural move at three layers, executed in three sequential phases on a single feature branch. Phase boundaries are verification gates, not commit boundaries — the implementation agent does not commit at any point.

1. **Schema layer** (Phase A): convert `FoodIntakeEvent` to a Pydantic discriminated union with one variant per `ActionType`. Each variant carries only the fields valid for that action. `LogFoodEvent` has `consumed_at`. `QueryStatsEvent` has `target_date` (single-day) XOR (`start_date` + `end_date`) (range). The union is enforced by `Annotated[Union[...], Field(discriminator="action")]` and a Pydantic `model_validator` on `QueryStatsEvent`. The LLM cannot emit `consumed_at` on a QUERY variant or range fields on a LOG variant — the JSON Schema served to OpenAI's structured-output mode physically excludes them per branch. **At the end of Phase A**, `input_parser_node` routes by `isinstance` of the typed result. The flat `AgentState` fields are still in place; they're populated from the matching variant for back-compat with downstream consumers (which are migrated in Phase B).
2. **State layer** (Phase B): introduce `LogFoodSubState` and `QueryStatsSubState` TypedDicts under `AgentState`. `input_parser_node` writes the matching sub-state on every turn (and `{}` for non-matching actions, so cross-turn residue is impossible). Migrate `commit_node`, `stats_node`, `response_node` to read from the sub-states. Delete the flat `consumed_at`/`start_date`/`end_date` fields from `AgentState`.
3. **Cleanup layer** (Phase C): with the sub-state structure in place, the audit residue smells become trivial fixes. Have `input_parser_node` clear `daily_log_report`, `pending_confirmations`, `search_results`, `selected_food_id` on every entry. Remove `commit_node`'s side-channel `daily_log_report` re-fetch. Verify `response_node` no longer injects `consumed_at` unconditionally (Phase B step already moved it; this is the final audit check).

After Phase A's tasks are done and verified, the working tree contains the user-visible bug fix. After Phase B, the architectural smell is gone but with one phase's worth of interim code (sub-states populated alongside flat fields, then the flat fields removed). After Phase C, the codebase is clean. **Only one commit at the very end**, triggered by the user.

## Feature Metadata

**Feature Type**: Refactor (architectural — three layers, single feature branch, single commit)
**Estimated Complexity**: Medium-High — 6 source files, 5 test files, 1 prompt, 2 doc updates; ~17 numbered tasks.
**Primary Systems Affected**:
- `src/schemas/input_schema.py` (Phase A — full rewrite to discriminated union)
- `src/agents/state.py` (Phase B — sub-states added; flat date fields removed)
- `src/agents/nodes/input_node.py` (Phase A action-routing; Phase B sub-state writes; Phase C clear-on-entry)
- `src/agents/nodes/commit_node.py` (Phase B sub-state read; Phase C side-channel removal)
- `src/agents/nodes/stats_node.py` (Phase B sub-state read)
- `src/agents/nodes/response_node.py` (Phase B sub-state read; Phase C verify gate)
- `prompts/input_parser.md` (Phase A — small tweak: QUERY date-field naming)
- `notebooks/evals/eval_input_parser_hebrew.py` (Phase A — re-key QUERY rows for `target_date`)
- `tests/conftest.py` (Phase B — `basic_state` fixture updates)
- New tests: `tests/unit/test_state_substates.py`, `tests/integration/test_log_yesterday_e2e.py`, `tests/graph_api/test_log_yesterday_flow.py`

**Dependencies**: None new. Pydantic v2 discriminated unions are supported by the installed `pydantic` and `langchain` versions — verified by Task 1 (Phase A0 smoke test) before any code change. `with_structured_output` accepts `Annotated[Union[...], Field(discriminator=...)]` per LangChain's structured-output documentation.

**Resolves**:
- The bug captured in `brain/planning/input-parser-state-nulling-by-fields-not-schema.md` (LangSmith trace `019dd286`).
- The audit's "explains/confirms the date bug" findings: `consumed_at` overloading, `input_parser_node` field-presence discriminator, `stats_node` priority chain (resolved by structure — sub-states have named fields, no polysemy), `commit_node` no fallback, `response_node` always-injection.

**Does NOT resolve** (out of scope — explicit guardrails):
- Other field-presence-as-discriminator sites: `route_after_calculate_macros` (audit smell #2), `confirmation_node:89-91` empty-batch shortcut (audit smell #3), `food_search_node:20-22` empty-pending shortcut (audit smell #4).
- `route_parser` routing of `QUERY_FOOD_INFO` through the LOG pipeline (audit open question; TASKS Important #14).
- `AMBIGUOUS` dead enum value (audit open question).
- `current_date` docstring drift (audit open question — `state.py:147` doc says it exists; the field doesn't).
- HITL natural-unit rendering bug (`brain/planning/hitl-confirmation-natural-unit-rendering.md` — separate fix; TASKS Important #7).
- Bot gateway, `src/services/*`, food catalog data, all prompts except `prompts/input_parser.md`, coach dashboard, `personal_stats_node`'s own schema (placeholder `LogPersonalStatsEvent` carries no fields; node uses its own extraction schema).
- Multi-turn eval cases of any kind (`brain/planning/multi-turn-eval-design-session.md`).

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

**Planning notes (mandatory pre-read)**:
- `brain/planning/input-parser-state-nulling-by-fields-not-schema.md` (full file) — discovery, root cause, sequencing.
- `brain/planning/state-lifecycle-audit.md` (full file) — Tables A + B + per-node narrative + cross-cutting findings. Anchors what's in scope vs. out of scope.

**Source files to modify**:
- `src/schemas/input_schema.py` (full file, 50 lines) — current flat `FoodIntakeEvent`. Lines 8-13 `ActionType` enum. Lines 16-30 `SingleFoodItem`. Lines 33-50 the flat `FoodIntakeEvent` to replace with the discriminated union.
- `src/agents/state.py` (lines 137-170) — `AgentState` TypedDict. Lines 162-164 are the flat date fields to remove in Phase B step 7. Line 147 `current_date` is a stale docstring entry — leave as-is (audit open question, separate fix).
- `src/agents/nodes/input_node.py` (full file, 82 lines) — bug site is lines 66-80 (the if-elif). Line 38-39 instantiates structured LLM with `FoodIntakeEvent`. Line 42 takes only the last message (`state["messages"][-1]`) — no conversation history sent to the LLM. Line 60-64 writes state.
- `src/agents/nodes/commit_node.py` (full file, 109 lines) — read site at lines 28-38 (timestamp fallback). Side-channel write at lines 95-100 + 102-106 return (Phase C step removes it).
- `src/agents/nodes/stats_node.py` (full file, 36 lines) — priority chain at lines 17-31. **Reads all three flat date fields without consulting `last_action`** (audit smell, resolved structurally in Phase B by reading from `query_stats` sub-state).
- `src/agents/nodes/response_node.py` (lines 153-196 specifically; full file 257 lines for surrounding helpers) — `_build_context` action gates ranges on lines 175-192 but injects `consumed_at` unconditionally on lines 162-168. Phase B step replaces these reads with sub-state reads.
- `src/agents/nutritionist.py` (full file, 99 lines) — graph topology. **Unchanged by this refactor.** Read it to understand the turn boundary (`input_parser` is sole entry; every terminal path goes through `load_daily_context → response → END`).

**Reference / read-only**:
- `prompts/input_parser.md` (full file, 163 lines) — system prompt. Lines 11-15 LOG_FOOD's `EXTRACT CONSUMED_AT` rules; lines 18-21 QUERY_DAILY_STATS' `EXTRACT DATES` rules. Phase A small edit: introduce `target_date` for QUERY single-day; the schema enforces the rest.
- `notebooks/evals/eval_input_parser_hebrew.py` (full file, ~763 lines) — 35 examples, 7 evaluators. The **only eval edit during the refactor** is re-keying QUERY-action examples to `target_date` (search for date-bearing examples in QUERY rows). Lines 443-454 the `run_input_parser` driver; lines 547-567 the new `no_query_dates_on_log_food` and `no_consumed_at_on_query` evaluators (kept as-is).
- `tests/conftest.py` (lines 27-58) — `_make_mock_runtime` and `basic_state` fixture (lines 44-58). Phase B step 7 updates `basic_state` to remove flat date fields and add `"log_food": {}` and `"query_stats": {}`.
- `src/config.py` (line 23: `USER_TIMEZONE = ZoneInfo("Asia/Jerusalem")`; line 51 `GLOBAL_MODEL`; lines 59-67 `NODE_CONFIGS`) — for any timezone-aware datetime construction in input_parser_node and stats_node.
- `docs/patterns/state-schemas.md` — three-layer state pattern (`InputState` → `AgentState` → `OutputState`). Sub-states live inside `AgentState` only.
- `docs/patterns/llm-config.md` — `get_llm_for_node()` and `with_structured_output()`. Discriminated union is passed exactly like a single BaseModel.
- `docs/plans/daily-log-loader-before-response.md` — most recent precedent for a state-shape change with a phased approach. Same convention this plan follows.
- `docs/plans/food-catalog-code-refactor.md` — second-most-recent precedent.

### New Files to Create

- `tests/unit/test_state_substates.py` — verifies `input_parser_node` always writes both `log_food` and `query_stats` keys (with `{}` for the non-matching action) on every turn. Defends against cross-turn residue. ~3-5 tests.
- `tests/integration/test_log_yesterday_e2e.py` — drives the graph for *"log X for yesterday"*, asserts the DB row's `timestamp` matches yesterday at noon Israel-local. Integration-tier mirror of the prod-bug repro.
- `tests/graph_api/test_log_yesterday_flow.py` — full HITL flow: user logs *"100g rice for yesterday"* → confirm via `command={"resume": "yes"}` → assert post-commit DB state matches yesterday.

### Relevant Documentation — YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [Pydantic v2 — Discriminated Unions](https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions-with-str-discriminators) — confirms `Annotated[Union[...], Field(discriminator="action")]` is the idiomatic shape. Each variant must declare `action: Literal[...]`.
- [Pydantic v2 — Model validators](https://docs.pydantic.dev/latest/concepts/validators/#model-validators) — `@model_validator(mode="after")` is the right tool for cross-field invariants like *"target_date XOR (start_date + end_date)"* on `QueryStatsEvent`.
- [LangChain — Structured output with Pydantic](https://python.langchain.com/docs/how_to/structured_output/#pydantic-model) — `with_structured_output(SomePydanticModel)` accepts a `BaseModel` subclass. For unions, pass the `Annotated[Union, Field(discriminator=...)]` alias; LangChain compiles to JSON schema with `oneOf` + discriminator.
- (Use the `docs-langchain` MCP server when verifying any signature against the installed version. The codebase is on LangChain 1.x — `pyproject.toml` has the exact pin.)

### Patterns to Follow

**Pydantic discriminated union** (target shape for `FoodIntakeEvent`):
```python
from typing import Annotated, List, Literal, Optional, Union
from datetime import date, datetime
from pydantic import BaseModel, Field, model_validator


class LogFoodEvent(BaseModel):
    action: Literal[ActionType.LOG_FOOD] = ActionType.LOG_FOOD
    items: List[SingleFoodItem] = Field(default_factory=list)
    meal_type: Optional[str] = None
    consumed_at: Optional[datetime] = Field(
        None,
        description=(
            "When the food was eaten. Hierarchy: exact time provided -> use exact "
            "time; relative (e.g. '2 hours ago') -> parse from injected system "
            "time; specific date (e.g. 'yesterday') -> that date at 12:00:00; "
            "no time mentioned -> leave null."
        ),
    )


class QueryStatsEvent(BaseModel):
    action: Literal[ActionType.QUERY_DAILY_STATS] = ActionType.QUERY_DAILY_STATS
    target_date: Optional[date] = Field(
        None,
        description="Single day being asked about (e.g. 'yesterday'). Null = today.",
    )
    start_date: Optional[date] = Field(
        None, description="Start of date range (inclusive). Range queries only."
    )
    end_date: Optional[date] = Field(
        None, description="End of date range (inclusive). Range queries only."
    )

    @model_validator(mode="after")
    def _exactly_one_shape(self) -> "QueryStatsEvent":
        has_target = self.target_date is not None
        has_range = self.start_date is not None and self.end_date is not None
        if has_target and has_range:
            raise ValueError(
                "QueryStatsEvent: target_date is mutually exclusive with start_date+end_date"
            )
        return self


class QueryFoodInfoEvent(BaseModel):
    action: Literal[ActionType.QUERY_FOOD_INFO] = ActionType.QUERY_FOOD_INFO
    items: List[SingleFoodItem] = Field(default_factory=list)


class LogPersonalStatsEvent(BaseModel):
    action: Literal[ActionType.LOG_PERSONAL_STATS] = ActionType.LOG_PERSONAL_STATS
    # Body of extraction continues to live in personal_stats_node's own schema.


class ChitchatEvent(BaseModel):
    action: Literal[ActionType.CHITCHAT] = ActionType.CHITCHAT


FoodIntakeEvent = Annotated[
    Union[
        LogFoodEvent,
        QueryStatsEvent,
        QueryFoodInfoEvent,
        LogPersonalStatsEvent,
        ChitchatEvent,
    ],
    Field(discriminator="action"),
]
```

**Action-isinstance routing in `input_parser_node`** (after Phase A):
```python
result = await structured_llm.ainvoke(messages)

# Discriminated union: result is one of the variant subclasses.
items: list[dict] = []
consumed_at: Optional[datetime] = None
start_date: Optional[date] = None
end_date: Optional[date] = None

if isinstance(result, LogFoodEvent):
    items = [item.model_dump() for item in result.items]
    consumed_at = result.consumed_at
elif isinstance(result, QueryStatsEvent):
    if result.target_date is not None:
        # Convert single-day target_date → noon Israel-local-as-UTC, so the
        # legacy stats_node fallback path (consumed_at.date()) keeps working
        # in Phase A. Phase B replaces this with a sub-state read.
        consumed_at = datetime.combine(
            result.target_date, time(12, 0), tzinfo=USER_TIMEZONE
        ).astimezone(timezone.utc)
    else:
        start_date = result.start_date
        end_date = result.end_date
elif isinstance(result, QueryFoodInfoEvent):
    items = [item.model_dump() for item in result.items]
# LogPersonalStatsEvent / ChitchatEvent: nothing to extract
```

**Sub-state TypedDict pattern** (target shape for `AgentState` in Phase B):
```python
class LogFoodSubState(TypedDict, total=False):
    """Per-action sub-state: meaningful only when last_action is LOG/CONFIRMED/LOGGED."""
    consumed_at: Optional[datetime]
    meal_type: Optional[str]


class QueryStatsSubState(TypedDict, total=False):
    """Per-action sub-state: meaningful only when last_action is QUERY_DAILY_STATS.

    target_date and (start_date, end_date) are mutually exclusive — enforced
    by QueryStatsEvent's model_validator at the LLM-output boundary.
    """
    target_date: Optional[date]
    start_date: Optional[date]
    end_date: Optional[date]
```

**Sub-state read pattern** (`commit_node` after Phase B step 3):
```python
log_food = state.get("log_food", {})
consumed_at = log_food.get("consumed_at")
```

**Cross-turn residue prevention** (`input_parser_node` after Phase B step 2):
```python
# Always write both keys — `{}` for non-matching actions. Overwrite-on-entry
# guarantees no leakage from a prior turn's sub-state.
log_food: LogFoodSubState = {}
query_stats: QueryStatsSubState = {}
if isinstance(result, LogFoodEvent):
    log_food = {"consumed_at": result.consumed_at, "meal_type": result.meal_type}
elif isinstance(result, QueryStatsEvent):
    query_stats = {
        "target_date": result.target_date,
        "start_date": result.start_date,
        "end_date": result.end_date,
    }

return {
    # ...
    "log_food": log_food,
    "query_stats": query_stats,
}
```

**Mocked-LLM unit test pattern** (the deterministic regression test):
```python
from unittest.mock import patch, AsyncMock, MagicMock
from langchain_core.messages import HumanMessage
from src.agents.nodes.input_node import input_parser_node
from src.schemas.input_schema import LogFoodEvent

@patch("src.agents.nodes.input_node.get_llm_for_node")
async def test_log_food_with_consumed_at_preserves_it(mock_get_llm):
    """Post-refactor: schema doesn't allow LogFoodEvent to carry range fields,
    so the bug shape is unrepresentable. Asserts consumed_at survives the node."""
    fake_result = LogFoodEvent(action="LOG_FOOD", consumed_at=YESTERDAY_18_UTC, items=[...])
    mock_llm = MagicMock()
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=fake_result)
    mock_llm.with_structured_output.return_value = structured
    mock_get_llm.return_value = mock_llm

    result = await input_parser_node({"messages": [HumanMessage(content="...")]})

    # Phase A assertion (flat fields still present):
    assert result["consumed_at"] == YESTERDAY_18_UTC
    assert result["start_date"] is None
    assert result["end_date"] is None

    # Phase B assertion (sub-states present):
    assert result["log_food"] == {"consumed_at": YESTERDAY_18_UTC, "meal_type": None}
    assert result["query_stats"] == {}
```

**Logging** (from `src/agents/nodes/commit_node.py:11`, `src/agents/nodes/input_node.py:11`):
```python
import structlog
logger = structlog.get_logger(__name__)
logger.info("Input parsed", action=result.action.value, items=len(items))
```

**Naming conventions**:
- Pydantic union variants: `<Action>Event` (`LogFoodEvent`, `QueryStatsEvent`, etc.)
- Sub-state TypedDicts: `<Action>SubState` (`LogFoodSubState`, `QueryStatsSubState`)
- AgentState keys: snake_case action names (`log_food`, `query_stats`)
- Existing `consumed_at` name preserved for LOG_FOOD's write timestamp; new `target_date` for QUERY's single-day lookup.

---

## IMPLEMENTATION PLAN

### Phase A — Schema split (the user-visible bug fix)

**Goal**: After Phase A's tasks are done and verified, the working tree contains the user-visible bug fix. The flat `AgentState` fields are still in place; only the schema and `input_parser_node`'s routing change. Downstream consumers continue to read the flat fields (back-compat).

**Tasks**: 1–6.

**Verification gate (must pass before moving to Phase B work)**:
- `uv run pytest tests/unit/ -v` green.
- `uv run pytest tests/integration/ -v` green.
- `uv run pytest tests/graph_api/ -v -s` green.
- `LLM_MODEL_NAME=gpt-5.4-mini uv run python notebooks/evals/eval_input_parser_hebrew.py` — `correct_dates ≥ 91.4%` (baseline); `no_query_dates_on_log_food` and `no_consumed_at_on_query` at 100%; non-temporal evaluators within ±2% of the baseline captured in Task 2.

**No commit at this gate.** The work continues on the same uncommitted working tree.

**Stop-and-ship fallback**: if Task 1 (Phase A0 smoke test) fails — i.e., `Annotated[Union[...], Field(discriminator=...)]` doesn't work with `with_structured_output` on the installed LangChain version — revert any schema changes on the working tree and apply this 5-line tactical fix at `input_node.py:67-80` instead:

```python
# Tactical fallback: action-based discriminator without schema changes.
if result.action == ActionType.QUERY_DAILY_STATS:
    updates["start_date"] = result.start_date
    updates["end_date"] = result.end_date
    updates["consumed_at"] = None
else:
    updates["consumed_at"] = result.consumed_at
    updates["start_date"] = None
    updates["end_date"] = None
```

This preserves the `consumed_at` value when action is LOG_FOOD even if the LLM also emits range fields — the bug is fixed at the read side. Defer Phases B/C post-POC. Capture the failure mode in `brain/planning/input-parser-state-nulling-by-fields-not-schema.md` and have the user trigger `/commit` for the tactical fix only.

### Phase B — AgentState sub-states

**Goal**: `AgentState` shape matches the schema shape. `consumed_at` / `start_date` / `end_date` no longer exist as flat fields — they live inside `log_food` / `query_stats` sub-states. Every reader (commit, stats, response) reads from the matching sub-state.

**Tasks**: 7–13.

**Verification gate (must pass before moving to Phase C work)**:
- All three test tiers green.
- Eval results within ±2% of baseline.
- `grep -rn 'state\[.consumed_at.\]\|state\.get(.consumed_at.)' src/` returns zero hits in production code.

**No commit at this gate.**

### Phase C — Cleanup

**Goal**: with the sub-state structure in place, the audit residue smells become trivial fixes. The codebase is clean.

**Tasks**: 14–17.

**Final verification gate**:
- All three test tiers green.
- Eval results stable (within ±2%).
- Manual smoke in dev bot (POLLING_MODE=true): three scenarios (see Task 17).

**No commit.** When Task 17 passes, **stop and return control to the user**. The user runs `/commit` to create the single refactor commit.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable. Do NOT skip the verification gate at the end of each phase. **Do NOT commit at any point.**

### Phase A

#### 1. SMOKE-TEST `Annotated[Union, Field(discriminator)]` × `with_structured_output` — canary

- **IMPLEMENT**: Run a one-shot inline check via `uv run python -c`:
  ```python
  import asyncio
  from typing import Annotated, Literal, Optional, Union
  from datetime import date
  from pydantic import BaseModel, Field
  from dotenv import load_dotenv
  load_dotenv()
  from langchain.chat_models import init_chat_model
  from src.config import GLOBAL_MODEL

  class LogFoodEvent(BaseModel):
      action: Literal["LOG_FOOD"] = "LOG_FOOD"
      consumed_at: Optional[str] = None

  class QueryStatsEvent(BaseModel):
      action: Literal["QUERY_DAILY_STATS"] = "QUERY_DAILY_STATS"
      target_date: Optional[date] = None

  class ChitchatEvent(BaseModel):
      action: Literal["CHITCHAT"] = "CHITCHAT"

  Union_t = Annotated[Union[LogFoodEvent, QueryStatsEvent, ChitchatEvent], Field(discriminator="action")]

  async def main():
      llm = init_chat_model(GLOBAL_MODEL, temperature=0).with_structured_output(Union_t)
      result = await llm.ainvoke([{"role": "user", "content": "I had an apple"}])
      print(type(result).__name__, result)

  asyncio.run(main())
  ```
- **PATTERN**: Mirrors how `input_parser_node:38-39` calls `with_structured_output(FoodIntakeEvent)`.
- **IMPORTS**: As shown.
- **GOTCHA**: If this command errors (`Unsupported schema`, JSON-schema compilation failure, or the result isn't an instance of any variant), the discriminated-union approach is **blocked on this codebase's LangChain version**. Apply the **stop-and-ship tactical fallback** documented in IMPLEMENTATION PLAN Phase A above — revert any schema changes (none made yet) and patch `input_node.py:67-80` with the 5-line action-based discriminator. Then jump to Task 5 to update `prompts/input_parser.md` (still useful), skip the eval re-key (Task 6 unchanged), run the verification gate, and stop. Do not proceed with Phases B/C.
- **VALIDATE**: Output prints one of `LogFoodEvent`, `QueryStatsEvent`, or `ChitchatEvent` with the correct fields populated. No exception. If success, continue to Task 2.

#### 2. CAPTURE eval baseline on the current `main` schema

- **IMPLEMENT**: Run the existing eval once to capture the pre-refactor baseline experiment. This is the comparison point for Task 6's verification (post-refactor scores must stay within ±2% of these on non-temporal evaluators).
  ```bash
  LLM_MODEL_NAME=gpt-5.4-mini uv run python notebooks/evals/eval_input_parser_hebrew.py
  ```
  Record the LangSmith experiment ID printed in the output (format: `input-parser-hebrew-gpt-5.4-mini-<hash>`).
- **PATTERN**: Standalone-eval execution. Mirrors how `input-parser-hebrew-gpt-5.4-mini-36a3dd0f` was captured earlier.
- **IMPORTS**: N/A.
- **GOTCHA**: The user's `.env` may have `LLM_MODEL_NAME=gpt-5.4-nano` for local. The inline `LLM_MODEL_NAME=gpt-5.4-mini` override matches prod and the experiment we'll compare against later. Don't forget the inline env var.
- **VALIDATE**: Eval runs to completion (35 examples × 7 evaluators); experiment ID captured.

#### 3. REWRITE `src/schemas/input_schema.py` to discriminated union

- **IMPLEMENT**: Replace the flat `FoodIntakeEvent` (lines 33-50) with the five variant classes (`LogFoodEvent`, `QueryStatsEvent`, `QueryFoodInfoEvent`, `LogPersonalStatsEvent`, `ChitchatEvent`) and the `FoodIntakeEvent = Annotated[Union[...], Field(discriminator="action")]` alias. Add a `model_validator(mode="after")` on `QueryStatsEvent` enforcing `target_date` XOR (`start_date` + `end_date`). Keep `ActionType` enum (lines 8-13) and `SingleFoodItem` (lines 16-30) unchanged. See *Patterns to Follow* for the full target shape.
- **PATTERN**: See *Patterns to Follow* — Pydantic discriminated union.
- **IMPORTS**: Add `Annotated`, `Union` from `typing`; `model_validator` from `pydantic`.
- **GOTCHA**:
  - `LogPersonalStatsEvent` carries no fields (placeholder); `personal_stats_node` continues to use its own `PersonalStatsExtraction` schema unchanged.
  - `ChitchatEvent` carries no fields. Pydantic v2 happily emits a model with only the discriminator literal.
  - `Literal[ActionType.LOG_FOOD]` may or may not work depending on Pydantic version — if discriminator field rejects enum literals, fall back to `Literal["LOG_FOOD"]` and have the variant default to the string value. Verify with `uv run python -c "from src.schemas.input_schema import FoodIntakeEvent, LogFoodEvent; LogFoodEvent()"`.
  - `QueryFoodInfoEvent` exists today as a routing target but `route_parser` currently sends it through the LOG pipeline (audit open question — out of scope here). The variant must still exist in the union or `with_structured_output` will reject any LLM emission with that action.
- **VALIDATE**:
  - `uv run python -c "from src.schemas.input_schema import FoodIntakeEvent, LogFoodEvent, QueryStatsEvent, ChitchatEvent; print('ok')"` — no errors.
  - `uv run python -c "from src.schemas.input_schema import QueryStatsEvent; QueryStatsEvent(action='QUERY_DAILY_STATS', target_date='2026-05-04', start_date='2026-05-04', end_date='2026-05-04')"` — must raise `ValidationError` (mutually exclusive).
  - `uv run python -c "from src.schemas.input_schema import QueryStatsEvent; print(QueryStatsEvent(action='QUERY_DAILY_STATS', target_date='2026-05-04'))"` — succeeds.

#### 4. MIGRATE `src/agents/nodes/input_node.py` to action-isinstance routing

- **IMPLEMENT**: Replace the if-elif at lines 66-80 with an isinstance dispatch. Keep the flat `consumed_at`/`start_date`/`end_date` writes for back-compat (Phase B introduces the sub-state writes alongside). Full body of the new return logic in *Patterns to Follow* — Action-isinstance routing.
- **PATTERN**: See *Patterns to Follow*.
- **IMPORTS**: Add `from datetime import date, datetime, time, timezone`. Add `from src.config import USER_TIMEZONE`. Add `from src.schemas.input_schema import LogFoodEvent, QueryStatsEvent, QueryFoodInfoEvent, LogPersonalStatsEvent, ChitchatEvent`.
- **GOTCHA**:
  - `last_message` (line 42) is unchanged — still single-message context.
  - `_current_time_str` (line 23-31) injection into the system prompt unchanged.
  - The flat `consumed_at` for QUERY single-day is computed from `target_date` to keep `stats_node`'s legacy `consumed_at.date()` fallback (lines 30-31) working until Phase B step 4 migrates the reader. Use `datetime.combine(result.target_date, time(12, 0), tzinfo=USER_TIMEZONE).astimezone(timezone.utc)` — Israel-local noon, converted to UTC for storage (matches how the existing `consumed_at` is treated).
  - `result.action.value` still works — every variant has `action: Literal[ActionType.<X>]` so `.value` returns the string.
- **VALIDATE**:
  - `uv run pytest tests/unit/test_input_parser_node.py -v` — adjust failing tests to the new shape if needed (existing tests may assert specific if-elif behavior).
  - Manual smoke: `uv run python -c "import asyncio; from langchain_core.messages import HumanMessage; from src.agents.nodes.input_node import input_parser_node; print(asyncio.run(input_parser_node({'messages': [HumanMessage(content='אכלתי בננה אתמול')]})))"` — should return `{..., "last_action": "LOG_FOOD", "consumed_at": <yesterday@12:00 UTC>, "start_date": None, "end_date": None}`.

#### 5. UPDATE `prompts/input_parser.md` — small QUERY date-field tweak

- **IMPLEMENT**: In the `### Step 1: Identify Intent (Action)` block:
  - Under **QUERY_DAILY_STATS** (lines 16-21), the **EXTRACT DATES** rule currently mentions only `start_date` and `end_date`. Add a sub-bullet for single-day:
    > *"For a single day (e.g., 'yesterday', 'last Tuesday', 'today'), set `target_date` to that date. Do not set `start_date`/`end_date` for single days."*
  - Under **LOG_FOOD** (lines 9-15), the **EXTRACT CONSUMED_AT** rule is unchanged.
  - Add a one-line invariant at the top of Step 1 (after line 7):
    > *"The schema enforces field semantics per action: LOG_FOOD uses `consumed_at`, QUERY_DAILY_STATS uses `target_date` OR (`start_date` + `end_date`). The Python schema rejects any other shape — do not mix."*
- **PATTERN**: Existing prompt format and tone (terse, bullet-heavy, examples).
- **IMPORTS**: N/A.
- **GOTCHA**:
  - Prompt tweaks can perturb eval scores. Run the full eval before+after and gate on ≤ ±2% movement on `correct_action`, `correct_serving`, `correct_item_count`, `food_name_quality`. The audit's "explains/confirms the date bug" findings are addressed structurally; the prompt edit is a soft hint that the schema enforces.
  - **Do not edit any other prompt file.** `response_generator.md`, `confirmation_parser.md`, etc. are out of scope.
- **VALIDATE**:
  - `LLM_MODEL_NAME=gpt-5.4-mini uv run python notebooks/evals/eval_input_parser_hebrew.py` — score deltas within ±2% on the non-temporal evaluators vs. Task 2 baseline.

#### 6. RE-KEY QUERY-action eval examples to `target_date`

- **IMPLEMENT**: In `notebooks/evals/eval_input_parser_hebrew.py` `EXAMPLES` list (lines 40-429), find every example where `action == "QUERY_DAILY_STATS"` AND `consumed_at` is a non-null sentinel (e.g., `"YESTERDAY_NOON"`). Move that sentinel to a new key `target_date` and set `consumed_at = None`. Range queries that already use `start_date`/`end_date` are unchanged. Update `_resolve_date_sentinel` (lines 509-530) and `correct_dates` (lines 570-597) to handle a `target_date` field comparison (mirror the existing `_dates_equivalent` logic — first-10-chars compare).

  Concretely:
  - Add `target_date` to the dict shape — `"target_date": Optional[str]`.
  - In `correct_dates`, after the `consumed_at` and `start_date`/`end_date` checks, add a `target_date` check: same `_dates_equivalent` logic.
  - In `run_input_parser` (lines 443-454), add `"target_date": str(result.get("target_date")) if result.get("target_date") else None`. **NOTE**: the post-refactor input_parser still writes flat `consumed_at`/`start_date`/`end_date` (Phase A is dual-write at the schema level only). The eval reads what the *node* returns. Decision: the eval continues to assert against the **flat fields** in Phase A. After Phase B, the eval is updated again to assert against sub-state contents. So this Task 6 is **only** about renaming the QUERY-row sentinel from `"consumed_at": "YESTERDAY_NOON"` to a flat-field shape that's still correct post-Phase-A. *Concrete decision*: in Phase A the input_parser converts QUERY single-day `target_date` → `consumed_at` at noon (back-compat), so QUERY-row eval examples that previously had `consumed_at: "YESTERDAY_NOON"` continue to be correct without changes. **Skip the QUERY rename in this task — keep `consumed_at: "YESTERDAY_NOON"` for QUERY rows in Phase A.** Run the eval to confirm.
  - The QUERY-row rename to `target_date` happens in Task 12 (Phase B step), once readers migrate to sub-states.
- **PATTERN**: Mirrors `correct_dates` evaluator's existing field-by-field check.
- **IMPORTS**: N/A.
- **GOTCHA**:
  - The dataset is keyed by question text (`existing_by_q` in `sync_dataset`), so example outputs being unchanged means `sync_dataset` reports "unchanged" (no upload needed).
  - The decision to skip the rename in Phase A is intentional — Phase A keeps the flat fields as the public contract for downstream consumers and tests. Phase B is when the eval-row shapes change.
- **VALIDATE**:
  - `LLM_MODEL_NAME=gpt-5.4-mini uv run python notebooks/evals/eval_input_parser_hebrew.py` — `correct_dates` ≥ 91.4%; `no_query_dates_on_log_food` and `no_consumed_at_on_query` at 100%; non-temporal scores within ±2% of Task 2 baseline.

#### 7. RUN Phase A verification gate

- **IMPLEMENT**: Run all four verification commands:
  ```bash
  uv run pytest tests/unit/ -v
  uv run pytest tests/integration/ -v
  uv run pytest tests/graph_api/ -v -s
  LLM_MODEL_NAME=gpt-5.4-mini uv run python notebooks/evals/eval_input_parser_hebrew.py
  ```
- **PATTERN**: Verification-gate pattern from `docs/plans/daily-log-loader-before-response.md`.
- **IMPORTS**: N/A.
- **GOTCHA**: **No commit at this point.** If any check fails, fix on the same uncommitted working tree before continuing to Phase B. Phase B's tasks layer on top of Phase A's work.
- **VALIDATE**: All four green. Eval criteria: `correct_dates` ≥ 91.4%; structural evaluators 100%; non-temporal scores within ±2% of Task 2 baseline.

---

### Phase B

#### 8. ADD `LogFoodSubState` and `QueryStatsSubState` TypedDicts to `src/agents/state.py`

- **IMPLEMENT**: After the existing TypedDict definitions (after `MacroResult`, around line 112), add `LogFoodSubState` and `QueryStatsSubState` TypedDicts with `total=False`. See *Patterns to Follow* — Sub-state TypedDict pattern. In `AgentState` (lines 137-170), add:
  ```python
  log_food: LogFoodSubState
  query_stats: QueryStatsSubState
  ```
  after `pending_confirmations` and before `daily_log_today`. **Keep flat `consumed_at` / `start_date` / `end_date` for now** — they're removed in Task 13.

  Update the `Attributes:` docstring in `AgentState` to describe `log_food` and `query_stats`. Mark the flat date fields as transitional (will be removed end of Phase B). Leave the stale `current_date` line in the docstring (audit open question, separate fix).
- **PATTERN**: Mirrors `PendingFoodItem`, `MacroResult`, etc. in the same file.
- **IMPORTS**: `date`, `datetime`, `Optional`, `TypedDict` already imported. No new imports.
- **GOTCHA**:
  - `total=False` means missing keys are valid. Sub-states default to `{}` (no keys present). `dict.get(key, default)` works as expected.
  - LangGraph's default reducer for non-`Annotated` state fields is overwrite-on-set. Sub-states will be fully overwritten on every input_parser_node return (Task 9 ensures this).
- **VALIDATE**:
  - `uv run python -c "from src.agents.state import AgentState, LogFoodSubState, QueryStatsSubState; assert 'log_food' in AgentState.__annotations__; assert 'query_stats' in AgentState.__annotations__; print('ok')"`.

#### 9. MIGRATE `input_parser_node` to dual-write (flat + sub-states)

- **IMPLEMENT**: In `src/agents/nodes/input_node.py`, extend the action-isinstance dispatch (Task 4) to also build `log_food` and `query_stats` dicts. Always include both in the return dict — `{}` for non-matching actions. See *Patterns to Follow* — Cross-turn residue prevention.

  Concretely, the return dict becomes:
  ```python
  return {
      "pending_food_items": items,
      "last_action": result.action.value,
      "processing_results": [],
      # Flat fields — back-compat for downstream consumers; removed in Task 13.
      "consumed_at": consumed_at,
      "start_date": start_date,
      "end_date": end_date,
      # Sub-states — new, primary going forward.
      "log_food": log_food,
      "query_stats": query_stats,
  }
  ```
- **PATTERN**: See *Patterns to Follow*.
- **IMPORTS**: `from src.agents.state import LogFoodSubState, QueryStatsSubState`.
- **GOTCHA**:
  - **Always write both sub-state keys** — even on non-matching actions write `{}`. This is the overwrite-on-entry guarantee. Don't optimize "skip if empty" — the explicit `{}` matters for clearing prior-turn residue.
  - LangGraph merges the dict into state with overwrite semantics for non-reducer fields. `{}` overwrites any prior value cleanly.
- **VALIDATE**:
  - Add `tests/unit/test_state_substates.py` with three tests:
    1. LOG turn writes `log_food.consumed_at` (when LLM provides it); `query_stats == {}`.
    2. QUERY range turn writes `query_stats.start_date`/`end_date`; `log_food == {}`.
    3. CHITCHAT turn writes both as `{}`.
    Each test mocks `get_llm_for_node` to return a fixed variant (see *Patterns to Follow* — Mocked-LLM unit test pattern).
  - `uv run pytest tests/unit/test_state_substates.py -v` — green.

#### 10. MIGRATE `commit_node` to read from `log_food` sub-state

- **IMPLEMENT**: In `src/agents/nodes/commit_node.py`, replace line 29:
  ```python
  consumed_at = state.get("consumed_at")
  ```
  with:
  ```python
  log_food = state.get("log_food", {})
  consumed_at = log_food.get("consumed_at")
  ```
  Lines 30-38 (the timestamp computation) are unchanged. Lines 95-100 (the conditional `daily_log_report` re-fetch) are **also still using `consumed_at`** — leave them as-is for now (Task 15 in Phase C removes the entire side-channel write).
- **PATTERN**: Sub-state read pattern from *Patterns to Follow*.
- **IMPORTS**: None new.
- **GOTCHA**:
  - `last_action` at this point is `"CONFIRMED"` (just entered commit). Don't gate on it — sub-state is the discriminator.
  - The conditional `daily_log_report` re-fetch at lines 95-100 is a separate finding — leave it for Task 15 (Phase C).
- **VALIDATE**:
  - `uv run pytest tests/unit/test_commit_node.py -v` — green.

#### 11. MIGRATE `stats_lookup_node` to read from `query_stats` sub-state

- **IMPLEMENT**: In `src/agents/nodes/stats_node.py`, replace lines 17-31 with:
  ```python
  query_stats = state.get("query_stats", {})
  target_date = query_stats.get("target_date")
  start_date_field = query_stats.get("start_date")
  end_date_field = query_stats.get("end_date")

  if start_date_field and end_date_field:
      report = await query_food_logs.ainvoke({
          "target_date": str(start_date_field),
          "end_date": str(end_date_field),
          "user_id": user_id,
      })
  elif target_date:
      report = await query_food_logs.ainvoke(
          {"target_date": str(target_date), "user_id": user_id}
      )
  else:
      # Default to today (Israel-local).
      today = datetime.now(USER_TIMEZONE).date()
      report = await query_food_logs.ainvoke(
          {"target_date": str(today), "user_id": user_id}
      )
  ```
  This retires the audit's smell #5 (priority chain on field-presence) — branching now uses **named sub-state fields**, not polysemous `consumed_at`.
- **PATTERN**: Sub-state read pattern.
- **IMPORTS**: Add `from src.config import USER_TIMEZONE` (line 1 area).
- **GOTCHA**:
  - The legacy `consumed_at.date()` fallback (line 31 of the old code) is removed. After Phase B, `stats_node` no longer reads `consumed_at` at all — single-day queries flow through `target_date`.
  - The today-fallback uses `datetime.now(USER_TIMEZONE).date()`, not `datetime.now(timezone.utc).date()`. This fixes a pre-existing maintenance bug (TASKS Maintenance #1) for free in this node only — the broader timezone-helper refactor stays out of scope.
- **VALIDATE**:
  - Update `tests/unit/test_stats_node.py` (or create if missing) with three tests: `target_date` branch, range branch, default-today branch. Use the `_make_mock_runtime` from `tests/conftest.py:27-33`.
  - `uv run pytest tests/unit/test_stats_node.py -v` — green.

#### 12. MIGRATE `response_node._build_context` to read from sub-states

- **IMPLEMENT**: In `src/agents/nodes/response_node.py`, modify `_build_context` (lines 153-196):
  - Lines 162-168 (the `consumed_at` always-injection): wrap in an action gate so it only injects on LOG-family actions:
    ```python
    if last_action in ("LOG_FOOD", "LOGGED", "CONFIRMED", "REJECTED"):
        log_food = state.get("log_food", {})
        consumed_at = log_food.get("consumed_at")
        if consumed_at:
            context["consumed_at"] = (
                consumed_at.isoformat()
                if isinstance(consumed_at, datetime)
                else str(consumed_at)
            )
    ```
  - Lines 175-192 (the QUERY_DAILY_STATS block): replace flat `state.get("start_date")` / `end_date` reads with sub-state reads, and add `target_date`:
    ```python
    elif last_action == "QUERY_DAILY_STATS":
        daily_log_report = state.get("daily_log_report", [])
        context["daily_log_report"] = daily_log_report

        query_stats = state.get("query_stats", {})
        target_date = query_stats.get("target_date")
        start_date = query_stats.get("start_date")
        end_date = query_stats.get("end_date")

        if target_date:
            context["target_date"] = (
                target_date.isoformat()
                if isinstance(target_date, date)
                else str(target_date)
            )
        if start_date:
            context["start_date"] = (
                start_date.isoformat()
                if isinstance(start_date, date)
                else str(start_date)
            )
        if end_date:
            context["end_date"] = (
                end_date.isoformat() if isinstance(end_date, date) else str(end_date)
            )
    ```
- **PATTERN**: Existing action-gated reads in the same function.
- **IMPORTS**: None new (`date`, `datetime` already imported on line 4).
- **GOTCHA**:
  - This combines Phase B's sub-state migration AND Phase C's "consumed_at always-injected" fix (audit separate finding). Doing both in one task is fine — the field is moving anyway, and gating it by action is the natural shape.
  - The `target_date` field is **new in the response_node JSON context**. The response_generator prompt may not know how to use it; check `prompts/response_generator.md` for any hard-coded references to `consumed_at` in QUERY context. **If editing response_generator.md, that is allowed under this refactor's scope** for field-name updates only (no behavior changes). Use `grep -n 'consumed_at\|start_date\|end_date' prompts/response_generator.md` to find any references.
- **VALIDATE**:
  - Update `tests/unit/test_response_node.py` to assert: (a) `consumed_at` is in context JSON only when `last_action ∈ {LOG_FOOD, LOGGED, CONFIRMED, REJECTED}`; (b) `target_date`/range fields are in context JSON only when `last_action == QUERY_DAILY_STATS`.
  - `uv run pytest tests/unit/test_response_node.py -v` — green.

#### 13. REMOVE the dual-write from `input_parser_node` AND delete flat date fields from `AgentState`

- **IMPLEMENT**: Two changes together:
  1. In `src/agents/nodes/input_node.py`, remove `"consumed_at"`, `"start_date"`, `"end_date"` keys from the return dict — only `log_food` and `query_stats` are written. Also remove the local-variable assignments (`consumed_at`, `start_date`, `end_date` and the QUERY single-day → noon conversion) since they're no longer needed; the sub-state dicts hold everything.
  2. In `src/agents/state.py`, delete lines 162-164 (the three flat date fields). Update the `Attributes:` docstring to drop them.
  3. In `tests/conftest.py` `basic_state` fixture (lines 44-58), remove `"consumed_at": None`, `"start_date": None`, `"end_date": None`. Add `"log_food": {}`, `"query_stats": {}`.
- **PATTERN**: Final cleanup of the dual-write transitional shape.
- **IMPORTS**: After deletion, check if `from datetime import time, timezone` is still used in `input_node.py` — if not, remove. Same for `USER_TIMEZONE` — keep if `_current_time_str` uses it (it does).
- **GOTCHA**:
  - All three readers (commit, stats, response) must be migrated before this task. Verify by grep:
    ```bash
    grep -rn 'state\[.consumed_at.\]\|state\.get(.consumed_at.)\|state\[.start_date.\]\|state\.get(.start_date.)\|state\[.end_date.\]\|state\.get(.end_date.)' src/agents/
    ```
    Should return zero hits in production code.
  - Any test file that constructs an `AgentState` literal with flat date fields will need updating. Check `tests/unit/test_*` for `"consumed_at":` and similar.
  - Update QUERY-row eval examples in `notebooks/evals/eval_input_parser_hebrew.py` to use the new flat→sub-state mapping in the eval's expected outputs. **Concrete approach**: extend `run_input_parser` (lines 443-454) to also expose `target_date` from `state["query_stats"]`, then re-key QUERY rows with non-null `consumed_at` sentinel to `target_date` instead. *Note*: the existing `correct_dates` evaluator already handles the `_resolve_date_sentinel` mapping for `YESTERDAY_NOON`; just point it at the new field. Run the eval and confirm scores stay within ±2%.
- **VALIDATE**:
  - `uv run pytest tests/unit/ -v` — green (all sub-state reads in place, no flat-field references).
  - `uv run pytest tests/integration/ -v` — green.
  - `uv run pytest tests/graph_api/ -v -s` — green.
  - `LLM_MODEL_NAME=gpt-5.4-mini uv run python notebooks/evals/eval_input_parser_hebrew.py` — `correct_dates ≥ 91.4%`; non-temporal scores within ±2% of Task 2 baseline.
  - `grep -rn 'consumed_at\|start_date\|end_date' src/agents/state.py` — no matches in `AgentState` (only inside `LogFoodSubState`/`QueryStatsSubState` and docstrings).

---

### Phase C

#### 14. ADD turn-entry clears in `input_parser_node`

- **IMPLEMENT**: In `src/agents/nodes/input_node.py`, add the following keys to the return dict (alongside `processing_results: []`):
  ```python
  "daily_log_report": [],
  "pending_confirmations": [],
  "search_results": [],
  "selected_food_id": None,
  ```
  These fields are turn-local (per the audit) but were previously cleared only by their consumers — leaving residue when consumers didn't run. Now `input_parser_node` resets them on every turn entry.
- **PATTERN**: Mirrors how `processing_results: []` is already cleared (existing line in input_node.py).
- **IMPORTS**: None new.
- **GOTCHA**:
  - This change closes the audit's "Fields that look turn-local but persist" findings.
  - `daily_log_today` is unaffected — it's loaded by `load_daily_context` immediately before `response`, fresh-by-construction.
  - `last_action` is overwritten by every node anyway — no clear needed.
  - Tests that depend on residue across turns (none expected, but verify) will fail here. Run the graph_api flow tests to surface any.
- **VALIDATE**: `uv run pytest tests/unit/ tests/integration/ tests/graph_api/ -v -s` — all green.

#### 15. REMOVE `commit_node`'s side-channel `daily_log_report` re-fetch

- **IMPLEMENT**: In `src/agents/nodes/commit_node.py`:
  - Delete lines 95-100:
    ```python
    # Fetch updated daily report
    updated_report = []
    if consumed_at:
        updated_report = await query_food_logs.ainvoke(
            {"target_date": str(consumed_at.date()), "user_id": user_id},
        )
    ```
  - In the return dict (lines 102-109), remove the `daily_log_report` key:
    ```python
    return {
        "pending_confirmations": [],
        "last_action": "LOGGED",
        "processing_results": processing_results,
        # daily_log_report removed — stats_lookup_node is now the sole writer
    }
    ```
  - Remove the now-unused import `from src.services.daily_log_service import ..., query_food_logs` if no other code in the file uses it. Check by `grep -n 'query_food_logs' src/agents/nodes/commit_node.py`.
- **PATTERN**: Reverts the side-channel write described in `brain/planning/state-lifecycle-audit.md` cross-cutting findings.
- **IMPORTS**: Remove `query_food_logs` from the `daily_log_service` import if unused.
- **GOTCHA**:
  - Tests in `tests/unit/test_commit_node.py` may assert that `daily_log_report` is updated post-commit. Drop those assertions — the audit confirmed this is a hack with no real consumer benefit (next-turn QUERY re-queries via stats_lookup anyway).
  - Phase C step 14's input_parser clear means `daily_log_report` is `[]` at the start of every turn unless `stats_lookup_node` runs. Verify this is acceptable — `response_node` reads it only when `last_action == "QUERY_DAILY_STATS"`.
- **VALIDATE**: `uv run pytest tests/unit/test_commit_node.py tests/integration/ tests/graph_api/ -v -s` — all green.

#### 16. VERIFY `response_node` `consumed_at` injection is fully gated

- **IMPLEMENT**: Re-read `_build_context` after Task 12. Confirm:
  - `consumed_at` injection is gated on `last_action ∈ {LOG_FOOD, LOGGED, CONFIRMED, REJECTED}` (or LOG-family).
  - `target_date`/`start_date`/`end_date` injection is gated on `last_action == "QUERY_DAILY_STATS"` only.
  - No state field is injected unconditionally except whatever was already always-on (e.g. `last_action` itself).
- **PATTERN**: Audit's `_build_context` (response_node.py:153-196) is the gold-standard contrast — already action-gated for most fields.
- **IMPORTS**: None.
- **GOTCHA**: If any state field is injected unconditionally that you didn't intend, that's another residue smell — flag as a separate finding by appending a one-line note to `brain/planning/state-lifecycle-audit.md` "Open questions / unclear cases" section. Don't fix in this refactor.
- **VALIDATE**: `grep -n 'context\[' src/agents/nodes/response_node.py` — every `context[key] = ...` is inside an action-gated block (LOG-family, QUERY_DAILY_STATS, or the unconditional `last_action` itself).

#### 17. RUN final verification gate + manual smoke + RETURN CONTROL TO USER

- **IMPLEMENT**: Run all three test tiers + eval + manual smoke test.

  Test tiers:
  ```bash
  uv run pytest tests/unit/ -v
  uv run pytest tests/integration/ -v
  uv run pytest tests/graph_api/ -v -s
  LLM_MODEL_NAME=gpt-5.4-mini uv run python notebooks/evals/eval_input_parser_hebrew.py
  ```

  Manual smoke (POLLING_MODE=true in dev bot):
  1. Log a single item: *"100g rice"* → confirm → ask *"מה אכלתי היום?"* — response includes the rice with today's timestamp.
  2. Log to yesterday: *"תוסיף לאתמול 100g chicken"* → confirm → query Supabase: the new row's `timestamp` is yesterday at noon Israel-local (or the time the LLM extracted), NOT today.
  3. Range query: *"מה אכלתי השבוע?"* → response covers the past 7 days.

  After all checks green, **stop and return control to the user**. Surface a concise summary:
  - What changed (files, lines)
  - Test/eval results
  - Manual smoke confirmation
  - Branch state: `refactor/discriminated-action-state`, working tree dirty (uncommitted), 0 commits added since the branch was created.

  **Do NOT call `git commit`. Do NOT call `git push`. Do NOT open a PR.** The user runs `/commit` to create the single refactor commit.
- **PATTERN**: Hand-off pattern. Working-tree-dirty hand-off; user owns the commit step.
- **IMPORTS**: N/A.
- **GOTCHA**:
  - If any verification fails, fix on the working tree before handing off. Do not partially commit.
  - **Confirm before stopping**: `git status` shows modified files; `git log --oneline | head -3` shows the branch's HEAD is unchanged from `main`'s HEAD at branch creation — no commits made.
- **VALIDATE**:
  - All three test tiers green.
  - Eval results: `correct_dates ≥ 91.4%`; `no_query_dates_on_log_food` and `no_consumed_at_on_query` at 100%; non-temporal scores within ±2% of Task 2 baseline.
  - Manual smoke: all three scenarios work.
  - `git status` shows the modified files; `git log refactor/discriminated-action-state ^main --oneline` returns empty (no new commits).

---

## TESTING STRATEGY

### Unit Tests

- `tests/unit/test_input_parser_node.py` (existing) — adjust assertions: post-Phase-A, `result["consumed_at"]` is set from the LogFoodEvent variant; post-Phase-B, `result["log_food"]["consumed_at"]` is the source of truth. Add cases for: LOG_FOOD with explicit yesterday, LOG_FOOD with no date, QUERY single-day, QUERY range, CHITCHAT.
- `tests/unit/test_commit_node.py` (existing) — read `consumed_at` from `state["log_food"]`. Drop assertions on the conditional `daily_log_report` re-fetch after Task 15.
- `tests/unit/test_stats_node.py` (new or extended) — three branches: `target_date` (single-day), range (`start_date+end_date`), default-today.
- `tests/unit/test_response_node.py` (existing) — assert `consumed_at` only injected in LOG-family contexts; assert `target_date`/range only in QUERY context.
- `tests/unit/test_state_substates.py` (new) — `input_parser_node` always writes `log_food` and `query_stats` (even as `{}` for non-matching actions); cross-turn residue is impossible by construction.

### Integration Tests

- `tests/integration/test_log_yesterday_e2e.py` (new) — drive the full graph for "log X for yesterday", assert the DB row's `timestamp` matches yesterday at noon Israel-local. The integration-tier mirror of the prod-bug repro from trace `019dd286`.
- Existing `tests/integration/test_daily_log_service.py` — service layer is unchanged; no edits needed.

### Graph-API Tests

- `tests/graph_api/test_log_yesterday_flow.py` (new) — full HITL: user sends *"log 100g rice for yesterday"* → `runs.wait` produces interrupt → `command={"resume": "yes"}` → assert post-commit DB state matches yesterday.
- Existing HITL flow tests under `tests/graph_api/` — re-run; should be unaffected by sub-state changes (confirmation_node doesn't touch dates).

### Edge Cases

- **LOG_FOOD with no date mentioned** — `log_food = {"consumed_at": None}`; commit_node falls back to `now()` (existing behavior, intentional).
- **QUERY_DAILY_STATS with no date mentioned** — `query_stats = {}`; stats_node defaults to today (Israel-local).
- **CHITCHAT turn after a LOG turn** — `log_food == {}`, `query_stats == {}`. No date residue in context.
- **HITL resume from confirmation** — graph re-enters at `confirmation_node`. Sub-states populated by the original input_parser turn are still in state (correct — the user is confirming the same food). Resume completes commit → load_daily_context → response.
- **Concurrent multi-item LOG** — `pending_food_items` loop drains items one-by-one; `log_food.consumed_at` is read by commit at the end and applies to all items. Existing behavior preserved.
- **Schema validator rejects mixed shape** — `QueryStatsEvent` with both `target_date` and `start_date+end_date` raises `ValidationError`. LangChain's `with_structured_output` either re-prompts or propagates the exception depending on config; either way the bug-shape is unrepresentable in the final state.

---

## VALIDATION COMMANDS

Execute every command at the relevant phase boundary. Zero regressions, 100% feature correctness.

### Level 1: Syntax & Style

```bash
uv run ruff check src/schemas/input_schema.py src/agents/state.py \
  src/agents/nodes/input_node.py src/agents/nodes/commit_node.py \
  src/agents/nodes/stats_node.py src/agents/nodes/response_node.py \
  tests/unit/test_state_substates.py tests/unit/test_input_parser_node.py \
  tests/unit/test_commit_node.py tests/unit/test_stats_node.py \
  tests/unit/test_response_node.py tests/conftest.py \
  tests/integration/test_log_yesterday_e2e.py \
  tests/graph_api/test_log_yesterday_flow.py
```

### Level 2: Unit Tests

```bash
uv run pytest tests/unit/ -v
```

### Level 3: Integration Tests

```bash
uv run pytest tests/integration/ -v
```

### Level 4: Graph-API Tests (mandatory — graph state shape changed)

```bash
uv run pytest tests/graph_api/ -v -s
```

### Level 5: LangSmith Eval (regression baseline comparison)

```bash
LLM_MODEL_NAME=gpt-5.4-mini uv run python notebooks/evals/eval_input_parser_hebrew.py
```

Compare the resulting experiment against the Task 2 baseline (`input-parser-hebrew-gpt-5.4-mini-<hash>` captured pre-refactor). Gate criteria:
- `correct_dates` ≥ 91.4% (baseline; should be higher).
- `no_query_dates_on_log_food` and `no_consumed_at_on_query` at 100%.
- `correct_action`, `correct_serving`, `correct_item_count`, `food_name_quality` within ±2% of baseline.

### Level 6: Manual Smoke (Telegram dev bot)

Run the bot with `POLLING_MODE=true`. Reproduce the three scenarios in Task 17.

### Level 7: Branch state check (handoff)

```bash
git status                                               # modified files, no commits
git log refactor/discriminated-action-state ^main --oneline  # empty — no new commits
```

---

## ACCEPTANCE CRITERIA

- [ ] `FoodIntakeEvent` is a Pydantic discriminated union with five variants (`LogFoodEvent`, `QueryStatsEvent`, `QueryFoodInfoEvent`, `LogPersonalStatsEvent`, `ChitchatEvent`).
- [ ] `QueryStatsEvent` has a `model_validator` enforcing `target_date` XOR (`start_date` + `end_date`).
- [ ] `AgentState` has `log_food: LogFoodSubState` and `query_stats: QueryStatsSubState`. Flat `consumed_at` / `start_date` / `end_date` are removed.
- [ ] `input_parser_node` writes both sub-states on every turn (`{}` for non-matching actions). Also clears `daily_log_report`, `pending_confirmations`, `search_results`, `selected_food_id` on every entry.
- [ ] `commit_node` reads `consumed_at` from `state["log_food"]`. No side-channel `daily_log_report` re-fetch.
- [ ] `stats_node` reads `target_date` / `start_date` / `end_date` from `state["query_stats"]`. Today-fallback uses `USER_TIMEZONE`.
- [ ] `response_node` injects `consumed_at` into context only on LOG-family actions; injects `target_date`/range only on QUERY action.
- [ ] Unit test with mocked LLM result preserves `consumed_at` post-refactor (deterministic regression test for the date bug).
- [ ] Graph-api test for "log to yesterday" passes — DB row's `timestamp` matches yesterday at noon Israel-local.
- [ ] All unit, integration, graph-API tests green.
- [ ] LangSmith experiment shows `correct_dates ≥ 91.4%`, `no_query_dates_on_log_food == 100%`, `no_consumed_at_on_query == 100%`, non-temporal scores within ±2% of Task 2 baseline.
- [ ] Manual smoke confirms log-to-yesterday lands on the correct DB date.
- [ ] No leftover references to flat `state["consumed_at"]` / `state["start_date"]` / `state["end_date"]` in `src/` (sub-state contents are fine).
- [ ] **Working tree is dirty (no commits made on the branch).** User triggers `/commit` to create the single refactor commit.

---

## COMPLETION CHECKLIST

- [ ] All 17 tasks completed in order
- [ ] Each task's `VALIDATE` step passed immediately
- [ ] `uv run ruff check` clean on every modified file
- [ ] Phase A verification gate green (Task 7) — no commit made
- [ ] Phase B verification gate green (after Task 13) — no commit made
- [ ] Final verification gate green (Task 17) — no commit made
- [ ] LangSmith comparison confirms `correct_dates ≥ 91.4%`, structural evaluators at 100%, non-temporal scores within ±2% of Task 2 baseline
- [ ] Manual smoke confirms all three scenarios in Task 17
- [ ] `git status` shows modified files; `git log refactor/discriminated-action-state ^main --oneline` is empty
- [ ] Implementation agent has stopped and returned control to the user (no commit, no push, no PR)
- [ ] CLAUDE.md update queued for `sync-context` (post-merge, by user): note the per-action sub-state pattern in the State Schemas row
- [ ] Discovery doc's "Sequencing" section updated (post-merge, by user): mark this refactor as shipped; mark TASKS Important #8 (HITL add-item) as the next coupled feature

---

## NOTES

### Why this design (vs. alternatives we considered)

Three other shapes were considered in `brain/planning/input-parser-state-nulling-by-fields-not-schema.md`:

- **Tactical 5-line fix only**: switch the if-elif's discriminator to `action`. Fixes the bug. Doesn't touch the architectural smell. Reserved as the **stop-and-ship fallback** if Task 1 (Pydantic-union canary) fails.
- **Defense-in-depth in `commit_node`**: when `consumed_at` is null, fall back to `start_date` if `start_date == end_date`. **Rejected** during planning — would entrench field-presence-as-discriminator at the read side. Range fields are query-scope; using them at the write boundary mixes semantics. The user explicitly caught this flaw.
- **Per-action sub-state without schema change**: keep flat `FoodIntakeEvent`, just route fields by `action` in `input_parser_node`. Half the architectural fix. Doesn't enforce invariants at the LLM-output boundary, so the LLM can still emit junk and the Python has to clean it up. Less robust than schema-level enforcement.

The discriminated union approach makes the broken state **structurally unrepresentable** — OpenAI's constrained decoder cannot emit `consumed_at` on a QUERY variant or range fields on a LOG variant because those fields don't exist in the JSON Schema branch served to it. Subsumes the tactical fix entirely.

### What is *not* changing

- Graph topology — entry, edges, terminal paths all unchanged. `load_daily_context → response → END` remains the response trail.
- `daily_log_today` — fresh-by-construction via `load_daily_context`. Untouched.
- `daily_log_report` — kept (different purpose from `daily_log_today`: arbitrary date or range). Lifecycle fixed (cleared on entry, single writer = stats_lookup), but no merge with `daily_log_today`.
- `personal_stats_node` — uses its own `PersonalStatsExtraction` schema. The `LogPersonalStatsEvent` placeholder in the union is empty.
- All prompts except `prompts/input_parser.md`. `prompts/response_generator.md` may need a one-line field-name update if it references `consumed_at` / `start_date` for QUERY context — that's allowed under the existing scope (Task 12 GOTCHA), but no behavioral changes.
- `bot/gateway.py`, `src/services/*`, food catalog data, coach dashboard.

### Known follow-ups (separate findings, NOT addressed here)

Per the audit's cross-cutting findings:
- `route_after_calculate_macros` field-presence routing on `pending_food_items`.
- `confirmation_node:89-91` empty-batch shortcut.
- `food_search_node:20-22` empty-pending shortcut.
- `route_parser` routing of `QUERY_FOOD_INFO` through the LOG pipeline (TASKS Important #14).
- `AMBIGUOUS` dead enum value.
- `current_date` docstring drift (`state.py:147`).
- HITL natural-unit rendering bug (`brain/planning/hitl-confirmation-natural-unit-rendering.md`; TASKS Important #7).
- `processing_results` overloading for stats vs. food entries (audit narrative).

After this refactor lands, run `sync-context` to update CLAUDE.md and re-run the audit pass to see which smells changed.

### POC deadline pressure

Today is 2026-05-04. POC is 2026-05-15 (~11 days out). At 2-3 h/day, ~17 numbered tasks fit in 7-9 working days — tight. **Stop-and-ship fallback** is built into Task 1: if the Pydantic-union canary fails, revert and apply the 5-line tactical fix. The audit and discovery docs preserve the design context so the deferred refactor (B/C) is straightforward to pick up post-POC.

### Confidence

**8/10** for one-pass implementation.

Lower than `daily-log-loader-before-response.md` (8.5/10) because:
- Discriminated union × `with_structured_output` compatibility is a known LangChain quirk; mitigated by Task 1 canary as the early signal.
- LangGraph's nested-TypedDict merge behavior — first-time pattern in this codebase. The plan handles it via "always overwrite sub-state on entry" but the assumption needs Task 9's tests to confirm.
- The QUERY-row eval re-key in Task 13 is mechanical but touches every QUERY-action example; one missed entry would skew the gate.

Risks **not** captured by the verification gates:
- Subtle response-prompt drift after the field-name rename in `response_generator.md` JSON context (if Task 12 needs that edit). Manual smoke is the only check.
- LangSmith dataset re-upload silently succeeds even on examples that didn't sync correctly. Spot-check the dataset UI after Task 13.

Sufficient confidence to execute. The discovery, audit, and this plan provide enough context that another engineer (or a fresh AI session) could pick up at any task without reload-cost.
