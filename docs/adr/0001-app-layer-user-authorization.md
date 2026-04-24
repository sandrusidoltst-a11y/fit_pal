# ADR-0001: App-layer user authorization via `user_id` scoping

- **Status**: Accepted 2026-04-25
- **Area**: auth, security
- **Deciders**: Dolev (with Claude Opus 4.7 as discussion partner)

## Context

FitPal is a multi-user Telegram bot on Supabase. Every DB table that holds user-specific data (`daily_logs`, `food_items`, `user_profiles`, `personal_stats_log`) has a `user_id` column and a foreign key to `auth.users(id)`. Users must only see their own data.

There are two distinct layers where that isolation can be enforced:

1. **In the application code** — every query explicitly filters `WHERE user_id = <current_user>`. The database trusts the code. The DB connection has superuser-adjacent privileges.
2. **In the database** — a scoped Postgres role plus Row-Level Security (RLS) policies. The application sets a user context at the start of each transaction; Postgres rewrites queries to enforce per-user visibility automatically.

Today's codebase uses layer 1. The architecture evolved this way organically during Phase 3 (Supabase migration) without an explicit decision recorded. The pragmatic reasons:

- The LangGraph service layer (`src/services/*.py`) uses SQLAlchemy async queries directly against Postgres via `asyncpg`. All call sites pass `user_id` as a function argument and include it in `WHERE` clauses.
- The bot opens sessions via `get_async_db_session()` in `src/database.py`, which returns a session connected via `SUPABASE_DB_URL` — the Supabase pooler URL for the `postgres` superuser role. This role **bypasses RLS by design**.
- Bot user registration uses `SUPABASE_SERVICE_KEY` (the Supabase service-role JWT) to call `auth.admin.create_user`. This key also bypasses RLS.
- RLS policies exist on `food_items`, `daily_logs`, and `personal_stats_log` ("defense in depth") but are not enforced against current traffic because both credentials the bot holds bypass them.

This came into focus on 2026-04-24 when a real user couldn't sign in and we traced it to a revoked legacy service-role JWT. The investigation surfaced the broader architectural question: is this the right model?

## Decision

**We keep user authorization at the application layer for the POC (mid-May 2026).**

Specifically:
- `user_id` continues to be passed explicitly through service functions, tools, and nodes.
- The bot continues to hold both `SUPABASE_DB_URL` (superuser) and `SUPABASE_SERVICE_KEY` (service-role).
- RLS policies remain in place as defense-in-depth but are not a primary enforcement mechanism.
- The immediate bug fix is a credential rotation (Supabase's new `sb_secret_...` key), not an architectural change.

We plan to revisit this decision post-POC and migrate to DB-layer authorization when the project warrants the investment.

## Alternatives considered

### Alternative A — Scoped DB role with `BYPASSRLS` (schema-level least privilege)

Create a dedicated Postgres role (e.g., `fitpal_bot`) with only `SELECT/INSERT/UPDATE/DELETE` on specific tables. Swap `SUPABASE_DB_URL` to connect as this role. Keep `BYPASSRLS` so no code changes are needed.

**Rejected for now because:**
- Meaningful but narrow benefit: removes the ability to `DROP TABLE`, access other schemas (`auth`, `storage`), create roles, etc. Does not reduce cross-user blast radius — a compromised bot still reads every user's data in granted tables.
- The "zero code changes" framing is misleading: it only holds if `BYPASSRLS` stays on. Without `BYPASSRLS`, RLS policies evaluate `auth.uid()` against a session context we don't set, returning zero rows silently.
- Deferred to the same window as Alternative B (see Revisit trigger below). Worth doing — just not in isolation.

### Alternative B — DB-layer RLS-enforced authorization

Create a scoped role *without* `BYPASSRLS`. Before every query, set `request.jwt.claims` to the acting user's identity so `auth.uid()` returns the correct UUID. Postgres enforces cross-user isolation at the database level.

**Rejected for POC because:**
- Requires a real refactor: every `async with get_async_db_session()` call site must plumb user identity through; `user_id` must move from function arguments to a contextvar or session-bound property; every `@tool` signature needs review to ensure tools don't *trust* user_id from LLM output.
- Estimated effort: 3–5 working days on the current codebase (small, clean service layer, tests in place).
- ROI is poor at POC scale (~10 friends and family). Real value lands when the first real coach uses the system and has their own trainees with private data.

This is the right long-term target. Not the right next step.

### Alternative C — Move registration to a Supabase Edge Function

Have the bot call a narrow edge-function endpoint to register users, keeping `SUPABASE_SERVICE_KEY` on Supabase's side.

**Rejected because:**
- Does not reduce attack surface while `SUPABASE_DB_URL` is also on the bot. A compromised bot still reads the DB directly via asyncpg, bypassing the edge function entirely.
- Adds a deploy dependency (edge-function lifecycle, versioning, cold-start latency) for no real blast-radius reduction.
- Would only become net-positive if paired with Alternative B, in which case the edge function is minor scaffolding.

## Consequences

### What this makes easier

- Short-term velocity. Every query is straightforward SQLAlchemy; no context plumbing.
- Testing. No need to mock `auth.uid()` or set session claims in unit/integration tests.
- Debugging. One authorization model to reason about.

### What this makes harder

- **Cross-user data leak risk is entirely in Python's hands.** A single omitted `WHERE user_id = ?` is a bug that leaks data across users. Nothing in the DB will catch it.
- **Bot compromise = full DB compromise.** Both credentials the bot holds (`SUPABASE_DB_URL` superuser, `SUPABASE_SERVICE_KEY` service-role) grant unrestricted data access. Any Python RCE via the bot is a full data-layer breach.
- **Harder to onboard a contractor or auditor.** An external reviewer looking at Supabase RLS policies would reasonably assume they enforce isolation. They don't, today, and that mismatch is surprising.
- **Future migration cost is real.** Moving to Alternative B later means touching every DB touchpoint, not a gradual path.

### What we are committing to

- **Every new service function must include `user_id` filtering.** The `tool-first` pattern already encodes this, but it is a human-enforced convention.
- **Name sanitization** becomes more important (the `name` field flows into LLM system prompts). Separate concern, but the same class of problem: untrusted input into a privileged context.
- **Passphrase-based access control** is our only barrier to registration. Strength matters.
- **Credential rotation discipline.** Both credentials are high-value and must be rotatable without code changes. The rotation discipline already exists via Railway env vars.

## Revisit trigger

Revisit this decision when **any** of the following is true:

1. **First real coach onboards** with their own trainees whose data must be isolated from other coaches' trainees. Multi-tenant isolation becomes a product requirement, not a future concern.
2. **A second backend service is added** that also needs DB access (e.g., the coach dashboard). Having two services each with superuser DB credentials amplifies the blast radius and complicates credential management.
3. **External contributors or contractors** start touching the codebase. Human-enforced conventions break faster with more hands.
4. **A data leak occurs** — or a near-miss — that traces to a missed `user_id` filter. Post-mortem should reopen this ADR.
5. **POC ships and the project enters Phase 4.** Scheduled re-evaluation, not crisis-driven.

At revisit, the recommended target is **Alternative B (DB-layer RLS enforcement)**, with **Alternative A as an intermediate step** if the full migration takes multiple sprints and an interim safety net is wanted.

## Related

- `DASHBOARD_PRD.md` — coach dashboard PRD. The enforcement-layer choice for the dashboard (lines 26, 46, 90) is the first place this ADR's trade-offs bite. See *"Consequences → What this makes harder"* and *"Revisit trigger → #2 second backend service"*.
- `bot/supabase_admin.py` — service-role key usage (`get_or_create_user`)
- `bot/gateway.py` — DB session usage on inbound messages
- `src/database.py` — `get_async_db_session()` factory
- `src/services/*.py` — service layer where `user_id` scoping is enforced today
- `docs/plans/phase3-auth-rls-telegram-gateway.md` — original Phase 3 plan (contains the one-line GOTCHA about `SUPABASE_SERVICE_KEY` bypassing RLS; predates this ADR)
- `docs/plans/remove-auth-pass-user-id-via-config.md` — swap from LangGraph custom auth handler to shared-secret middleware (moved the service-role key from `langgraph-server` to `fitpal-bot`)
- `brain/planning/onboarding-security-audit.md` — sibling concern: prompt injection via `name` field and SQL injection audit
- `CLAUDE.md` — tech stack table notes "service role bypasses" RLS (the only prior acknowledgment in the codebase)
