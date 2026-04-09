# Architecture Pattern Files + CLAUDE.md Reorganization

**Commit**: `8d7959e`
**Branch**: `Menu-and-Personal-Details`
**Date**: 2026-04-09

## Changes

### New Pattern Files (`.claude/patterns/`)
- **tool-first.md**: Three-layer pattern (service fn → @tool wrapper → node), serialization boundary, session lifecycle, when to add/skip wrappers, 12 hard rules.
- **llm-config.md**: `get_llm_for_node()` factory, `NODE_CONFIGS` hierarchy, Pydantic structured output (`.with_structured_output(Schema)`), `.model_dump()` only at state boundary, `response_node` conversational carve-out, prompt loading at module level, 12 hard rules.
- **hitl-confirmation.md**: `interrupt()` loop, `Command(goto=...)` dynamic routing, batch accumulation via `MacroResult`, `_parse_confirmation` structured output, edit pipeline (`_apply_edits` with reverse-removal and DB-vs-estimated branching), Telegram relay contract, 10 hard rules.
- **schema-management.md**: UUID PKs, `user_id` scoping conventions, FK to `auth.users` in Postgres only (not SQLAlchemy), timestamp patterns (event vs audit, lambda defaults), `create_all()`/`drop_all()` prohibition in prod, 9 hard rules.

### CLAUDE.md Reorganization
- Pattern table trimmed from 11 to 7 entries (only reusable code patterns).
- Fixed misleading `.model_dump()` claim in LLM config summary — now correctly states "call `.model_dump()` only at the state-write boundary".
- New **"Architectural Decisions (future ADRs)"** section preserves 4 non-pattern descriptions (off-menu estimation, auth + tagged users, bot gateway, data flow) for future migration to `docs/adr/`.

### PRD.md Phase 4 Additions
- **HITL add-item edit type gap**: Documents silent-drop behavior when user mixes confirm + new items.
- **Routing style audit**: Documents `Command` vs `add_conditional_edges` tradeoffs for future evaluation.

## Pattern Files — Final Status (7/7 complete)

| File | Created |
|---|---|
| `runtime-context.md` | Prior session |
| `state-schemas.md` | Prior session |
| `async-patterns.md` | Prior session |
| `tool-first.md` | This session |
| `llm-config.md` | This session |
| `hitl-confirmation.md` | This session |
| `schema-management.md` | This session |

## Next Steps
- Set up `docs/adr/` directory with ADR template and README
- Migrate the 4 architectural decisions from CLAUDE.md into proper ADR files
- Consider seeding 2-3 retroactive ADRs for load-bearing decisions (tool-first, fully-async, HITL+Command)
