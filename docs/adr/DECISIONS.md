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
