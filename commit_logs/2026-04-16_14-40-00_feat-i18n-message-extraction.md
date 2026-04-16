# feat: extract user-facing bot/agent strings into YAML i18n module

**Date**: 2026-04-16
**Branch**: i18n-message-extraction
**Commit**: 936caf7

## Changes

### New `src/i18n/` package
- `__init__.py` — `Messages` TypedDict (21 keys), `_load_yaml`, `_validate_parity`, `_resolve_language`, `_load_messages_from_paths` (pure function for testing), and module-level `MESSAGES = _load_messages()`
- Strict parity check at import time: collects ALL violations (missing/extra keys, empty values, non-string values across en/he/TypedDict) and raises one `ValueError` with the full picture
- `BOT_LANGUAGE` env var resolution: `en` default, `he` supported, anything else raises
- File path resolution via `Path(__file__).parent` (avoids prior `os.getcwd()` BlockingError pattern)

### YAML files
- `src/i18n/en.yaml` — 21 English strings, flat keys grouped by prefix (`onboarding_*`, `auth_*`, `error_*`, `confirmation_*`)
- `src/i18n/he.yaml` — 21 Hebrew skeleton values (`TODO_HE: <english>`), parity-valid so loader boots; intentional loud prefix until translated

### Refactored callsites
- `bot/gateway.py` — 17 inline string literals replaced with `MESSAGES[...]` lookups; `ONBOARDING_QUESTIONS` dict replaced with `_onboarding_question(step)` helper that reads from `MESSAGES`; `_format_interrupt_value` now uses `confirmation_macro_line` and `confirmation_total_line` templates with `.format(...)` placeholders
- `src/agents/nodes/confirmation_node.py` — 2 strings replaced (`confirmation_question`, `confirmation_estimated_tag`)

### Tests
- `tests/unit/test_i18n.py` — 22 new tests across `TestResolveLanguage`, `TestValidateParity`, `TestLoadMessagesFromPaths`, `TestRealMessagesModule`. Uses `tmp_path` for fixture YAMLs to test failure modes without touching real `src/i18n/*.yaml`
- `tests/unit/test_gateway.py` — 4 literal-string assertions converted to `gw.MESSAGES[...]` lookups

### Docs / config
- `pyproject.toml` + `uv.lock` — `pyyaml>=6.0.3` promoted from transitive to direct dep via `uv add pyyaml`
- `PRD.md` — Phase 4 backlog entry for "Per-User Language Preference" (stored on `UserProfile`, allows mixed-language trainees on one bot)
- `README.md` — new "Localization" section documenting `BOT_LANGUAGE` env var, the requirement to set it on both Railway services, and how to add new strings

## Validation

| Check | Result |
|---|---|
| `ruff check` (changed files) | ✅ all checks passed |
| `pytest tests/unit/` | ✅ 121 passed |
| `pytest tests/integration/` | ✅ 30 passed (75s) |
| Manual: `BOT_LANGUAGE=en` | ✅ loads English |
| Manual: `BOT_LANGUAGE=he` | ✅ loads Hebrew skeleton |
| Manual: `BOT_LANGUAGE=fr` | ✅ ValueError fail-fast |
| `.dockerignore` audit | ✅ YAMLs included in image |

## Out of scope / follow-ups

1. **Latent bug in `_format_interrupt_value`**: the `(estimated)` tag is appended twice — once by `_format_batch_preview` baking it into `description`, once by the bot render. Localized via single key but the duplication remains. Worth a separate cleanup commit.
2. **Substring assertion in `test_onboarding.py:165`** (`"number" in ...`) left alone — language-tolerant for now, will need rework when Hebrew strings land.
3. **Per-user locale (v2)** — backlogged in PRD Phase 4. Adds `UserProfile.language` column and per-call language selection.

## Next Steps

- **Translate Hebrew skeleton**: replace `TODO_HE: <english>` lines in `src/i18n/he.yaml` with real Hebrew. Loader will continue to boot before this is done — Hebrew bot just shows the literal `TODO_HE:` prefix.
- **Smoke test via dev bot**: run `uv run python -m bot.gateway` with `POLLING_MODE=true`, send a message, verify English replies are unchanged.
- **When ready to deploy Hebrew**: set `BOT_LANGUAGE=he` on **both** the `langgraph-server` and `fitpal-bot` Railway services in the same deploy. Mismatched env vars → half-translated chats.
