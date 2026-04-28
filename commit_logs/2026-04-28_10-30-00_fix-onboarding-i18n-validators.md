# fix: onboarding validators (gender Hebrew aliases + height decimal comma) + config doc note

**Date**: 2026-04-28
**Branch**: main
**Commits**:
- `51e2e76` — `fix: accept Hebrew aliases for gender + decimal comma for height in onboarding`
- `2802566` — `docs: note LLM_MODEL_NAME default is local-only; prod is set on Railway`
**Source**: `brain/planning/onboarding-validators-partial-localization.md` (Fix 1 + Fix 2)

## What changed

### 1. `bot/gateway.py` — onboarding validator i18n (commit `51e2e76`)

Hebrew users hit a silent infinite loop on the gender step after sign-in: the bot prompted in Hebrew (`גבר או אישה ?`) but the validator at `bot/gateway.py:244` only accepted English literals (`male` / `female` / `other`). The bot's "invalid" reply also used the same Hebrew words it refused to accept — so typing `גבר` got rejected and the user was told to type `גבר`. A friend hit this on 2026-04-25.

Two surgical fixes from the planning note:

- **Fix 1 (gender)** — added a module-level `GENDER_ALIASES` map covering English + Hebrew variants (`גבר`/`זכר` → `male`, `אישה`/`אשה`/`נקבה` → `female`, `אחר` → `other`, plus shortcuts like `m`/`f`). Validator normalizes input then looks it up; canonical English value is still what gets stored downstream, so DB / response_node prompts see no change.
- **Fix 2 (height decimal comma)** — `float(text.replace(",", "."))` so European-style `1,80` works alongside `1.80`. One-line defensive addition.

Skipped intentionally:
- **Fix 3 (age)** — no known break.
- **Fix 4 (structured logging on onboarding)** — separate task; the real fix to prevent future silent loops, but not blocking the friend.
- **Fix 5 (move aliases to YAML)** — architectural, post-POC.

### 2. `src/config.py` — env-var doc note (commit `2802566`)

Discovered prod was still running `gpt-4o` because `LLM_MODEL_NAME` had been set on Railway long ago and the local default in `config.py` wasn't being read. Added a comment above `GLOBAL_MODEL` noting that the default is local-only and prod is controlled by the Railway env var on `langgraph-server`. Prevents the next "I edited the default, why didn't it change" moment.

Prod model also swapped from `gpt-4o` → `gpt-5.4-mini` via Railway (separate ops change, not a code change).

## Validation

- `uv run ruff check bot/gateway.py`: passed
- `uv run pytest tests/unit/`: 155 passed (1.32s)

Integration / graph-api not re-run — change is contained to bot transport layer + a comment.

## Files

- `bot/gateway.py` — added `GENDER_ALIASES` constant; gender validator normalizes-then-looks-up; height parser strips European decimal comma.
- `src/config.py` — 4-line comment above `GLOBAL_MODEL`.

## Next steps

Continuing UX cleanup from the train session, ordered by priority in `brain/TASKS.md` Important section:

- **#2** — Audit recent bot conversations in LangSmith for macro-accuracy issues (post-Plan-3 dogfood signal). Especially relevant now that prod model just changed to `gpt-5.4-mini`; baseline shifts.
- **#3** — Verify deletion from DB is working.
- **#4** — Budget-reasoning template in `response_node` prompt (audit Fix #6).
- **#6** — Language-consistency rule in `response_node` prompt (audit Fix #4) — cheap.
- **#11** — Unit-vocabulary fallback rule in `prompts/input_parser.md` — exact text already drafted in TASKS.md.

## Out of scope / known follow-ups

- No unit test added for the Hebrew gender path. The bug had no test guardrail; the planning note flags adding one as the right follow-up but train session prioritized the surgical fix. Add when picking up the broader i18n sweep.
- Onboarding still has zero structured logging (Fix 4). Future onboarding-stage bugs will remain silent until that lands.
- Validator aliases hardcoded in Python rather than i18n YAML (Fix 5) — fine for two languages, fragile beyond that.
