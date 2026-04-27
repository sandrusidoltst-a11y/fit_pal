# RCA: Plan 3d incomplete migration + tool-first drift in `load_daily_context_node`

**Date investigated**: 2026-04-26
**Surfaced by**: PR review of commit `93c2d2d` (ADR-0003 implementation)
**Status**: Two related issues, both being fixed in `docs/plans/loader-tool-first-via-query-food-logs-backfill.md`
**Severity**: Low — no user-visible incident; legacy stats path silently rendered without coach-method category breakdown, a degraded-but-functional experience

## Symptoms

1. **Tool-first violation** — `src/agents/nodes/load_daily_context_node.py` imports `get_async_db_session` from `src.database` and opens its own DB session inside the node. CLAUDE.md is explicit: *"All DB access through async @tool functions. Nodes are thin orchestrators via `await tool.ainvoke(...)` — never import DB sessions."* The PR review caught this immediately.
2. **Missing coach-mapping data in legacy stats path** — When the user asked "what did I eat this week?" via `stats_lookup_node` → `query_food_logs` → `daily_log_report`, the rendered system prompt was missing the per-category totals block. The new `daily_log_today` injection (Plan 3d) correctly carried mappings, but the older `daily_log_report` path did not.

## Root cause analysis

### Issue 1 — tool-first drift in the new node

The plan that introduced `load_daily_context` (`docs/plans/daily-log-loader-before-response.md`, executed in commit `93c2d2d`) was tightly focused on the staleness-bug fix from LangSmith thread `73ed31fb-…` and the ContextSchema → AgentState refactor. The plan's "Patterns to Follow" section even referenced the right shape — *"Async DB session pattern (used inside `@tool` wrappers in `src/services/daily_log_service.py:260-274`)"* — but then in the same breath instructed the executor to use that pattern *inside the node itself*, not inside a tool. The convention violation was baked into the plan, not introduced during execution.

**Why the plan got it wrong**: the executor needed `_serialize_log` with the coach-mapping join, which only `get_todays_logs_serialized` (a service function) provided. The existing `query_food_logs` tool didn't have the join (see Issue 2). Faced with "use the wrong tool" or "violate convention," the plan picked convention-violation. Neither option was named explicitly during planning — the constraint that forced the choice was invisible.

### Issue 2 — Plan 3d's parallel-implementation migration

Plan 3d (food catalog "Plan 3" trilogy + serving-math, commits `b562262` and following, 2026-04-?) introduced coach-method category data into the daily log render path. It added:

- `_serialize_log(log, mapping=None)` — extended to optionally embed `category` / `tag` / `serving_amount_g` from a coach mapping.
- `get_logs_by_date_with_mappings(session, user_id, date)` — new helper that LEFT-JOINs `coach_food_mappings` and returns `(DailyLog, Optional[CoachFoodMapping])` tuples.
- `get_todays_logs_serialized(session, user_id)` — new helper used by the daily-log injection path; calls `get_logs_by_date_with_mappings` internally.

It did **not** migrate the existing `query_food_logs` tool to use the new helper. The legacy `get_logs_by_date` and `get_logs_by_date_range` functions were left in place as the only callers from inside `query_food_logs`. No `get_logs_by_date_range_with_mappings` helper was added — Plan 3d only handled the single-date case it directly needed.

**Why the migration was incomplete**: Plan 3d's scope was the new injection path (Fix #2 from the bot UX audit). It added the with-mappings variant *for that path*, not as a general upgrade. The legacy callers stayed working with the un-joined data — the regression was silent (degraded output, not a crash), so nothing forced the migration to complete.

### The link between the two issues

The PR planning surfaced this connection: the cleanest fix for Issue 1 (use a tool, not a service function) requires that some tool returns the coach-mapping data the loader needs. The only tool that *could* do that — `query_food_logs` — has the Plan 3d gap. So Issue 2 is a precondition for cleanly fixing Issue 1.

## Underlying pattern (the bug class)

Two anti-patterns, observed together but distinct:

### Pattern A — "migration via parallel implementation"

When a richer-shape function is added **alongside** a legacy one (instead of mutating the legacy in place or deleting it), legacy callers don't auto-migrate. Each caller silently keeps the older, less-rich shape. The codebase ends up with two functions doing almost the same thing, with subtly different outputs, and no compiler/linter forces the unification.

**Why it happens**: the plan author scopes their work narrowly to the path they're adding. The legacy callers aren't on their critical path, so they aren't migrated. Tests for the new function pass, the new path works, the legacy path also still works — nothing fails.

**Detection**: any service module with `_with_mappings`, `_v2`, `_with_X` style sibling functions where legacy callers still exist. Easy to grep:

```bash
grep -rn "get_logs_by_date\b\|search_food_items\b" src bot --include='*.py'
# Compare against grep for the *_with_mappings variant
```

If the legacy variant has callers other than the new variant itself, those callers are migration candidates.

### Pattern B — "convention drift via plan-induced shortcuts"

When a plan needs to ship something fast and runs into a constraint that violates an unspoken convention, the plan can quietly bake in the violation — and the auto-generated tests + docs match the violation, so the violation looks "consistent."

**Why it happens**: planning is a single-pass exercise. Conventions live in CLAUDE.md, which the planner reads but doesn't always cross-reference against the implementation it's prescribing. The violation is invisible at planning time; only PR review catches it.

**Detection**: any node opening `get_async_db_session` or any other "framework hook" that the convention says belongs in `@tool` wrappers. Easy to grep:

```bash
grep -rn "get_async_db_session\|from src.database" src/agents/nodes --include='*.py'
# Should return nothing — graph nodes never touch the engine directly.
```

The grep above caught the violation in this RCA; would have caught it during planning too.

## Where else might these patterns hide?

Audit performed 2026-04-26:

### Tool-first compliance (graph nodes)

```text
food_search_node       → search_food (tool)                           ✅
personal_stats_node    → log_personal_stat (tool)                     ✅
stats_node             → query_food_logs (tool)                       ✅
confirmation_node      → calculate_food_macros (tool)                 ✅
commit_node            → log_food_entry, query_food_logs,             ✅
                          create_food_item (tools)
calculate_macros_node  → calculate_food_macros (tool)                 ✅
load_daily_context_node → get_async_db_session +                      ❌ (fixed by current plan)
                          get_todays_logs_serialized (service fn)
```

Only one violation, isolated to the new node introduced by commit `93c2d2d`.

### Parallel-implementation migrations (daily_log_service)

```text
get_logs_by_date          → only caller is query_food_logs            ❌ (legacy still in use)
get_logs_by_date_range    → only caller is query_food_logs            ❌ (legacy still in use; range with-mappings doesn't exist)
get_logs_by_date_with_mappings → only caller is get_todays_logs_serialized (deleted by current plan)
```

### Parallel-implementation migrations (food_service)

```text
search_food_items     → in-place migrated; returns (FoodItem, mapping) tuples; only one variant exists  ✅
get_food_by_id        → in-place migrated; returns (FoodItem, mapping) tuples; only one variant exists  ✅
```

`food_service.py` migrated in place (no parallel implementation), so the food path is consistent. The `daily_log_service.py` miss is isolated.

### Gateway DB access

```text
bot/gateway.py:204  _save_user_profile  → opens session directly      ⚠️ (transport layer; convention ambiguous)
bot/gateway.py:217  _load_user_profile  → opens session directly      ⚠️
```

**Strictly** the convention says "All DB access through async @tool functions." The gateway opens sessions directly for onboarding/profile fetch. This is **out of scope for the current plan** because:
- The gateway is the transport layer, not a graph node — the convention text explicitly addresses *nodes* ("Nodes are thin orchestrators").
- The gateway runs *outside* the graph runtime, so there's no obvious tool to call (no `runtime` parameter, no graph context).
- It's been this way since the bot's original implementation; no change in this PR caused it.

Worth a separate, explicit decision: should the gateway also be tool-first (creating `@tool get_user_profile(user_id)` and `@tool save_user_profile(user_id, data)` wrappers), or does the convention legitimately exclude transport-layer code? If the latter, CLAUDE.md should clarify the carve-out.

## Preventive measures

Three concrete steps to catch these patterns earlier in the future.

### 1. Pre-merge grep checks (cheapest, deploy now)

Add to the PR template (or as a CI lint):

```bash
# Tool-first invariant: nodes never touch the DB engine directly.
test -z "$(grep -rln 'get_async_db_session\|from src.database' src/agents/nodes --include='*.py')" \
  || { echo "FAIL: graph node imports DB session"; exit 1; }

# Optional: legacy-helper-still-in-use audit
# Manual sweep: any function with a *_with_X sibling whose legacy variant
# still has non-trivial callers is a migration candidate.
```

### 2. Plan-time convention checklist

For any plan that adds a node, add a checklist item:

> **Tool-first compliance**: the new node only calls `@tool` functions or other nodes; it imports neither `get_async_db_session` nor any service function that requires a session. If you can't satisfy this, the plan must either (a) add a `@tool` wrapper for the data shape it needs, or (b) explicitly justify the violation in the plan body.

This forces the constraint that bit us into being visible at planning time.

### 3. Migration-completeness review when adding `_with_X` variants

For any plan that adds a parallel-implementation function (e.g. `_with_mappings`, `_v2`, etc.) instead of mutating in place, add a checklist item:

> **Migration completeness**: list every existing caller of the legacy function; either migrate them in this plan or explicitly defer with a tracked follow-up. Parallel implementations without a migration plan create silent drift.

## Resolution

Both issues are being fixed in `docs/plans/loader-tool-first-via-query-food-logs-backfill.md`:

1. **Tool-first restored**: `load_daily_context` becomes a thin orchestrator calling `query_food_logs.ainvoke({...})`.
2. **Plan 3d backfill completed**: `query_food_logs` migrated to use the with-mappings variants on both branches; new helper `get_logs_by_date_range_with_mappings` added; dead `get_todays_logs_serialized` removed.

Side benefit: the `daily_log_report` field (populated by `query_food_logs` for the `stats_lookup → response` path and the `commit_node` refresh) now also carries coach-mapping data, so the legacy stats path reaches feature parity with the new daily-log injection path.

## Related

- `docs/adr/0003-daily-log-loader-before-response.md` — the loader's design decision; this RCA addresses the implementation drift, not the design.
- `docs/plans/loader-tool-first-via-query-food-logs-backfill.md` — the resolution plan.
- `docs/patterns/tool-first.md` — the convention this RCA refers to.
- `commit_logs/2026-04-26_09-40-00_refactor-daily-log-loader-before-response.md` — the commit that introduced Issue 1 (with full context on why it shipped as-is).
- LangSmith thread `73ed31fb-8391-4c97-a05f-a4b672c6fcd5` — the original bug audit that started this whole sequence.
