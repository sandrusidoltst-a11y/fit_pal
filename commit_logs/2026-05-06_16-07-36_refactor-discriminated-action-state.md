# refactor: per-action state via discriminated FoodIntakeEvent + sub-states

**Commit**: `15d715e`
**Branch**: `refactor/discriminated-action-state`
**Plan**: `docs/plans/discriminated-action-state-refactor.md`

## What changed

Replaced the flat `consumed_at` / `start_date` / `end_date` fields on `AgentState` with two per-action sub-states (`log_food`, `query_stats`), backed by a typed union at the LLM-output boundary:

```
FoodIntakeEvent (BaseModel wrapper)
└── event: LogFoodEvent | QueryStatsEvent | QueryFoodInfoEvent
              | LogPersonalStatsEvent | ChitchatEvent
```

Each variant carries only the fields valid for its action. `QueryStatsEvent` has a `model_validator` enforcing `target_date` XOR (`start_date` + `end_date`). The LLM cannot emit `consumed_at` on a QUERY variant or range fields on a LOG variant — those fields don't exist in the variant's JSON Schema.

## Why

LangSmith trace `019dd286` (2026-04-28): user wrote *"תוסיף לאתמול עוד פיתה"*, the LLM emitted both `consumed_at = 2026-04-27T18:00Z` AND `start_date/end_date = 2026-04-27`, the input_parser's if-elif kept the range fields and **nulled `consumed_at`**, and `commit_node` fell back to `datetime.now()`. Six items got written with today's timestamp.

After this refactor the bug shape is structurally unrepresentable.

## File-by-file

| File | Change |
|---|---|
| `src/schemas/input_schema.py` | Discriminated union of 5 variants + `FoodIntakeEvent` BaseModel wrapper. |
| `src/agents/state.py` | Added `LogFoodSubState`, `QueryStatsSubState`. Removed flat `consumed_at`/`start_date`/`end_date`. |
| `src/agents/nodes/input_node.py` | Action-isinstance routing; always writes both sub-state keys (`{}` for non-matching action). Phase C turn-entry clears: `daily_log_report`, `pending_confirmations`, `search_results`, `selected_food_id`. |
| `src/agents/nodes/commit_node.py` | Reads `consumed_at` from `state["log_food"]`. Removed side-channel `daily_log_report` re-fetch (`stats_lookup_node` is sole writer). |
| `src/agents/nodes/stats_node.py` | Reads `target_date`/`start_date`/`end_date` from `state["query_stats"]`. Today-fallback now uses `USER_TIMEZONE`. |
| `src/agents/nodes/response_node.py` | `_build_context`: gated `consumed_at` injection to LOG-family; reads dates from sub-states; injects `target_date` for QUERY. |
| `prompts/input_parser.md` | Schema invariant note + `target_date` guidance for QUERY single-day. |
| `notebooks/evals/eval_input_parser_hebrew.py` | Driver reads from sub-states; `correct_dates` + `no_query_dates_on_log_food` cover `target_date`. |
| `tests/conftest.py` | `basic_state` fixture: dropped flat date fields, added empty sub-states. |
| `tests/unit/test_state_substates.py` (new) | Cross-turn residue guard — `input_parser_node` always writes both sub-state keys. |
| `tests/integration/test_log_yesterday_e2e.py` (new) | Deterministic regression: `commit_node` lands the DB row on yesterday-Israel-local when `log_food.consumed_at` is set. |
| `tests/graph_api/test_log_yesterday_flow.py` (new) | Live-LLM HITL flow: *"log 100g chicken for yesterday"* → interrupt → confirm → `log_food.consumed_at` lands on yesterday. |
| `tests/unit/test_{commit,stats,response,input_parser}_node.py` | Updated to sub-state shape. |

## Verification

- **Unit**: 159 passed.
- **Integration**: 47 passed (incl. new `test_log_yesterday_e2e`).
- **Graph-API**: 14 passed (incl. new `test_log_yesterday_flow`).
- **Ruff**: clean.
- **Eval** (`gpt-5.4-mini`, experiment `input-parser-hebrew-gpt-5.4-mini-cc6bb8c5`):
  - `correct_action`: 100%
  - `correct_dates`: **91.4%** (= baseline `36a3dd0f`)
  - `correct_item_count`: 100%
  - `correct_serving`: 87.1%
  - `food_name_quality`: 100%
  - `no_consumed_at_on_query`: **100%** ✅
  - `no_query_dates_on_log_food`: **100%** ✅

## Plan deviation worth flagging

The plan called for `Annotated[Union[...], Field(discriminator="action")]` as the LLM schema. This blew up twice with `with_structured_output`:

1. Plain `Annotated[Union[...]]` isn't a class → LangChain's `convert_to_openai_function` rejects.
2. Wrapped in `RootModel` → top-level `oneOf` → OpenAI strict mode rejects (top must be `type: object`).
3. Wrapped in a `BaseModel` with `event: Annotated[Union[...], Field(discriminator=...)]` → still emits `oneOf` → OpenAI strict mode rejects (only `anyOf` is allowed).

**Final shape**: `class FoodIntakeEvent(BaseModel): event: Union[LogFoodEvent, ...]` — no discriminator hint, so Pydantic emits `anyOf` and uses smart-union mode for runtime variant selection via each variant's `Literal[ActionType.X]` action field. Field-isolation at the schema level is preserved.

The constraint is documented inline in the `FoodIntakeEvent` docstring.

## Next steps

- Manual smoke (deferred per Task 17): three Telegram dev-bot scenarios with `POLLING_MODE=true`:
  1. *"100g rice"* → confirm → *"מה אכלתי היום?"* — today's log includes the rice.
  2. *"תוסיף לאתמול 100g chicken"* → confirm → DB row's `timestamp` is yesterday at the LLM-extracted time.
  3. *"מה אכלתי השבוע?"* → range query covers past 7 days.

- Open the PR for review.

- Audit residue not addressed by this refactor (per plan):
  - `route_after_calculate_macros` field-presence routing on `pending_food_items`.
  - `confirmation_node:89-91` empty-batch shortcut.
  - `food_search_node:20-22` empty-pending shortcut.
  - `route_parser` routing of `QUERY_FOOD_INFO` through the LOG pipeline (TASKS Important #14).
  - `AMBIGUOUS` dead enum value.
  - `current_date` docstring drift (`state.py:147`).
  - HITL natural-unit rendering bug (TASKS Important #7).
