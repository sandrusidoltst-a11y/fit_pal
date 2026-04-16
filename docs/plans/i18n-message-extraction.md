# Feature: i18n Message Extraction (English + Hebrew skeleton)

The following plan should be complete, but it is important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files etc.

## Feature Description

Extract every hardcoded user-facing string in the FitPal bot and graph into a YAML-backed i18n module (`src/i18n/`). Strings live in `en.yaml` and `he.yaml`; a `Messages` TypedDict defines the contract; a loader picks the language at startup via the `BOT_LANGUAGE` env var (`en` default, `he` for Hebrew); and a strict parity check crashes the process at import time if the two YAML files don't have identical keysets matching the TypedDict.

This unblocks giving the FitPal Telegram bot to Hebrew-speaking users (Dolev's brother and friends — Goal 3: First Real Users) by making the entire bot UI flippable to Hebrew via a single env var on Railway, with no further code changes once Hebrew strings are filled in.

## User Story

As Dolev (the developer/coach)
I want to flip every prewritten bot message to Hebrew via a single env var
So that I can hand the bot to my Hebrew-speaking brother and friends without forking the code or maintaining a separate branch.

## Problem Statement

Today, ~22 user-facing strings are scattered across two files (`bot/gateway.py`, `src/agents/nodes/confirmation_node.py`) as inline string literals: onboarding questions, validation errors, welcome messages, generic error fallbacks, the HITL confirmation question, and the macro-line render labels (`"kcal"`, `"P:"`, `"Total:"`, `"Reply 'yes' to confirm…"`).

This means:
1. Translating the bot to Hebrew requires hunting through code and editing every string in place.
2. There is no way to ship a bilingual codebase — the live language is whatever was last hardcoded.
3. Translation-prone bugs (e.g., missing a string when adding a new feature) are caught only by manual QA.

## Solution Statement

Create `src/i18n/` as the single source of truth for user-facing strings:
- **`Messages` TypedDict** — declares every key the system uses; gives static type safety on lookups.
- **`en.yaml` + `he.yaml`** — flat key→string mapping per language.
- **Loader (`__init__.py`)** — at import time: load both YAMLs, validate that their keysets exactly match the TypedDict's annotations, pick one based on `BOT_LANGUAGE` env var, expose as `MESSAGES`.
- **Strict parity check** — if `he.yaml` is missing a key that `en.yaml` has (or vice versa, or either has keys not in the TypedDict), `raise ValueError` with the missing key list. The bot/server process refuses to start until the YAMLs are in sync.
- **Callsite refactor** — replace the ~22 inline literals with `MESSAGES["..."]` lookups. Strings with placeholders (`{name}`, `{cals}`, etc.) are formatted with `.format(...)` at the callsite.

In v1: one global language per Railway service (set `BOT_LANGUAGE=he` on both `langgraph-server` and `fitpal-bot`). Per-user locale (stored in `UserProfile.language`) is backlogged in PRD Phase 4 and explicitly out of scope here.

## Feature Metadata

**Feature Type**: Refactor (no behavior change at EN; new capability at HE)
**Estimated Complexity**: Low-Medium — small string surface, but touches two services that must stay in sync at deploy time.
**Primary Systems Affected**:
- `bot/gateway.py` (Telegram bot process)
- `src/agents/nodes/confirmation_node.py` (LangGraph node, runs in langgraph-server process)
- New: `src/i18n/` package
- Tests: `tests/unit/test_i18n.py`, updates to `tests/unit/test_gateway.py` and `tests/unit/test_confirmation_node.py`
- `PRD.md` (Phase 4 backlog entry for per-user locale)

**Dependencies**: `pyyaml` (already in `uv.lock` as transitive — promote to direct dep via `uv add pyyaml`)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: YOU MUST READ THESE BEFORE IMPLEMENTING

- `bot/gateway.py` (full file, lines 1-466) — every user-facing string in the bot lives here; understand the full callsite context before refactoring. Strings are concentrated at:
    - Lines 46-51 — `ONBOARDING_QUESTIONS` dict (already a constant; replace with i18n lookups)
    - Lines 151-186 — `_format_interrupt_value()` — the bot's HITL preview render with `"kcal"`, `"P:"`, `"C:"`, `"F:"`, `"Total:"`, and the `"Reply 'yes' to confirm…"` footer
    - Lines 222, 228, 232 — onboarding validation errors
    - Lines 262-264 — onboarding completion (`"Great, {name}!..."`)
    - Lines 285-287 — thread-creation error
    - Line 338 — empty-response fallback
    - Lines 342-344, 347-349 — HTTP/generic processing errors
    - Line 356 — non-text-message response
    - Lines 392-394, 397-399 — welcome / welcome-back messages
    - Lines 402-404 — registration failure
    - Line 406 — invite-code prompt

- `src/agents/nodes/confirmation_node.py` (lines 29-57) — `_format_batch_preview()` produces the HITL interrupt payload. Two strings to extract:
    - Line 33 — `" (estimated)"` source-tag suffix
    - Line 54 — `"Please review the following items before I log them. You can confirm, reject, or edit specific items."`
    - **Note**: line 37 also formats item descriptions as `"{food_name} — {amount_g}g{source_tag}"`. The `"g"` (grams) and the em-dash separator are arguably user-facing but are unit/punctuation concerns; treat as language-neutral and leave as-is for v1. The plan does not localize these.

- `src/config.py` (full file, lines 1-84) — env var loading pattern with `os.getenv(...)`, `dotenv.load_dotenv()` already called, and how new module-level constants are declared. Mirror this pattern in `src/i18n/__init__.py` for `BOT_LANGUAGE`.
    - Line 16: `BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` — **do not** use `os.getcwd()` to locate i18n files (caused a prior `BlockingError` incident, see memory). Use `Path(__file__).parent` for files inside `src/i18n/` itself.

- `prompts/response_generator.md` (line 20) — confirms the LLM-generated coach responses already handle language matching (`"Match the user's language. Hebrew in → Hebrew out."`). This is why response_node strings stay out of scope.

- `tests/unit/test_gateway.py` (lines 1-80) — pytest test conventions (AAA docstrings, `AsyncMock`/`MagicMock`, fixtures). New i18n tests should match this style.

- `tests/unit/test_confirmation_node.py` (lines 1-60) — shows how `_format_batch_preview` is unit-tested today. Update tests to assert against the localized strings.

- `pyproject.toml` (full file, lines 1-44) — direct deps live in `[project].dependencies`. Add `pyyaml>=6.0.3` here (matching the version already pinned in `uv.lock`).

- `bot/Dockerfile` and `langgraph.production.json` — already build the Docker image with everything under `bot/` and `src/`. The new `src/i18n/` package and its `*.yaml` files will be included automatically since they live under `src/`. **Verify** by inspecting `.dockerignore` in step 7 below to confirm `*.yaml` is not excluded.

- `CLAUDE.md` — project rules; relevant excerpts:
    - "Never hardcode models" / "use existing patterns" — same spirit applies to i18n (don't hardcode strings; use `MESSAGES["…"]`).
    - "Fully Async" — i18n loader runs at import time, synchronously. That's fine: `yaml.safe_load` of two small files at startup is not on the async path. **Do not** make the loader async.

### New Files to Create

- `src/i18n/__init__.py` — loader, `Messages` TypedDict, `MESSAGES` constant, validation logic
- `src/i18n/en.yaml` — English strings (fully populated)
- `src/i18n/he.yaml` — Hebrew skeleton (same keys as `en.yaml`, values are empty strings or English placeholders that Dolev fills in himself; loader treats empty strings as valid — this is by design so Dolev can fill them progressively without breaking startup, BUT the parity check still fires if any key is missing entirely)
    - **Decision point during implementation**: treat empty string `""` as valid (Dolev fills in over time) OR require non-empty strings (forces all-or-nothing). Recommendation: **require non-empty** for v1, because an empty Hebrew message would show as a blank Telegram bubble in prod. Force Dolev to either fill it or use the English fallback string explicitly. Implementation: if any HE value is empty, parity check raises with "key X has empty value in he.yaml — fill it in or copy the English value".
- `tests/unit/test_i18n.py` — loader tests (parity validation, env var selection, placeholder preservation, error cases)

### Files to Modify

- `bot/gateway.py` — replace ~17 string literals with `MESSAGES["…"]` lookups
- `src/agents/nodes/confirmation_node.py` — replace 2 string literals
- `tests/unit/test_gateway.py` — update assertions that pin exact English strings (e.g. `assert_called_once_with("Send the invite code to get started.")` becomes `assert_called_once_with(MESSAGES["auth_invite_prompt"])`)
- `tests/unit/test_confirmation_node.py` — same for confirmation node assertions
- `pyproject.toml` — add `pyyaml>=6.0.3` to `[project].dependencies`
- `PRD.md` — append a new pending bullet under `### Phase 4: Polish & Intelligence` (around line 510, after "Routing Style Audit")
- `README.md` — add a short "Localization" section under or near the "Local Bot Development" block: env var name, supported values, default, how to translate

### Relevant Documentation — YOU SHOULD READ THESE BEFORE IMPLEMENTING

- [PyYAML safe_load docs](https://pyyaml.org/wiki/PyYAMLDocumentation#loading-yaml)
    - Specific section: `yaml.safe_load` — never use `yaml.load` (arbitrary code execution risk on untrusted input). Both `en.yaml` and `he.yaml` are repo-controlled, but use `safe_load` anyway as a defensive default.
- [Python TypedDict — runtime introspection](https://docs.python.org/3/library/typing.html#typing.get_type_hints)
    - Specific section: `typing.get_type_hints(MyTypedDict)` — returns `{"key": str, ...}`. Use this in the loader to programmatically derive the expected key set from the TypedDict, so adding a new field to the TypedDict automatically requires both YAMLs to add it. Avoids drift between Python annotations and YAML reality.
- [Python str.format placeholder behavior](https://docs.python.org/3/library/string.html#format-string-syntax) — relevant for `onboarding_complete` (`{name}` placeholder), `confirmation_macro_line`, `confirmation_total_line`. Use `.format(name=...)` or `.format(**kwargs)` at callsite. Prefer named placeholders over positional for clarity.
- [Telegram Bot API — UTF-8 handling](https://core.telegram.org/bots/api#sendmessage) — Telegram natively handles UTF-8 (Hebrew, RTL). No special headers or encoding required. Hebrew strings just work.

### Patterns to Follow

**Naming Conventions**:
- File: `snake_case.py` for module, `snake_case.yaml` for data files (`en.yaml`, `he.yaml`)
- Constants: `UPPER_SNAKE_CASE` (`MESSAGES`, `SUPPORTED_LANGS`, `DEFAULT_LANG`, `I18N_DIR`)
- Module-level types: `PascalCase` (`Messages`)
- YAML keys: `snake_case`, flat (no nesting). Group via prefix: `onboarding_*`, `auth_*`, `error_*`, `confirmation_*`.

**Env Var Loading Pattern** (mirror `src/config.py` lines 28-31):
```python
import os
import structlog

logger = structlog.get_logger(__name__)

LANG = os.environ.get("BOT_LANGUAGE", "en").lower()
logger.info("i18n language resolved", language=LANG)
```
- Use `os.environ.get(...)` (not `os.getenv` — both work but the codebase uses `os.environ.get` for module-level env reads in `bot/gateway.py:34-41`). Both styles exist; pick `os.environ.get` for consistency with bot/gateway since this module is most often imported by the bot.

**File Path Pattern** — never use `os.getcwd()` (BlockingError incident in memory):
```python
from pathlib import Path
I18N_DIR = Path(__file__).parent
EN_FILE = I18N_DIR / "en.yaml"
HE_FILE = I18N_DIR / "he.yaml"
```

**Logging Pattern** (project uses `structlog`):
```python
logger = structlog.get_logger(__name__)
logger.info("i18n loaded", language=lang, key_count=len(messages))
logger.error("i18n parity check failed", missing_in_en=sorted(en_missing), missing_in_he=sorted(he_missing))
```
- Use keyword args, not f-strings inside `logger.info(...)`.

**Test Conventions** (from `tests/unit/test_gateway.py` and `tests/unit/test_confirmation_node.py`):
- File header docstring with `Scope:` and `LLM Usage:` sections
- Class-based grouping (`class TestParityCheck:`, `class TestLoaderEnvVar:`, etc.)
- AAA docstrings on every test method (`arrange:` / `act:` / `assert:` lines)
- `pytest.raises` for error-path tests, with the exception's message asserted via `match=...` regex when reasonable
- `monkeypatch.setenv("BOT_LANGUAGE", "he")` for env-var manipulation (don't mutate `os.environ` directly)

**TypedDict + Runtime Validation Pattern** (new in this codebase):
```python
from typing import TypedDict, get_type_hints

class Messages(TypedDict):
    onboarding_welcome: str
    # ... other keys

EXPECTED_KEYS = set(get_type_hints(Messages).keys())
```
- This is the textbook way to derive a runtime keyset from a TypedDict. `get_type_hints` works with TypedDict in Python 3.13.
- Cite this in a one-line comment so the next developer understands why the TypedDict is the source of truth.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation (Module Structure + Dependency)

Set up the i18n package skeleton and lock the YAML dependency before any code that uses it lands.

**Tasks**:
- Add `pyyaml` as a direct dependency in `pyproject.toml` via `uv add pyyaml`.
- Create the `src/i18n/` package (directory + `__init__.py`).
- Define the full `Messages` TypedDict with all ~22 keys upfront — this is the contract everything else conforms to.

### Phase 2: YAML Files

Populate `en.yaml` with the existing English strings (1:1 mapping, no rewriting). Create `he.yaml` skeleton with the same key list and explicit `TODO_HE` placeholder values that Dolev will replace.

**Tasks**:
- Write `src/i18n/en.yaml` with every key the TypedDict declares, value = the current English string from the source file (verbatim, including punctuation and placeholders).
- Write `src/i18n/he.yaml` with the same keys, value = `"TODO_HE: <english string>"` so Dolev can grep for `TODO_HE` later. The parity check (Phase 3) treats these as valid non-empty strings — they only become a problem when the bot is run with `BOT_LANGUAGE=he` because users will see the literal `TODO_HE` prefix. That's intentional: it makes "this isn't translated yet" loud.

### Phase 3: Loader + Parity Check

The core logic that makes the system fail-fast and type-safe.

**Tasks**:
- In `src/i18n/__init__.py`: implement `_load_yaml(path)`, `_validate_parity(en, he, expected_keys)`, `_load_messages()`, and module-level `MESSAGES = _load_messages()`.
- Parity check covers: (a) keys in TypedDict missing from EN, (b) keys in TypedDict missing from HE, (c) keys in EN not in TypedDict, (d) keys in HE not in TypedDict, (e) empty-string values in either file. All errors collected and raised as a single `ValueError` with all violations listed (not first-error-only).
- Validate `BOT_LANGUAGE` env var: must be in `("en", "he")`. Reject unsupported values with a clear error. Fall back to `"en"` if env var is unset.
- Log the resolved language and key count at INFO level on successful load.

### Phase 4: Callsite Refactor

Replace inline string literals at all the points enumerated in CONTEXT REFERENCES.

**Tasks**:
- In `bot/gateway.py`: import `MESSAGES`. Replace each literal with the corresponding lookup. For format-string literals (`f"Great, {name}!..."`), use `.format(name=name)` on the localized template (`MESSAGES["onboarding_complete"].format(name=name)`).
- Convert the `ONBOARDING_QUESTIONS` dict (lines 46-51) into a function or property that reads from `MESSAGES`. Recommendation: replace the dict with a small helper:
  ```python
  def _onboarding_question(step: str) -> str:
      return MESSAGES[f"onboarding_q_{step}"]
  ```
  Then call `_onboarding_question(next_step)` instead of `ONBOARDING_QUESTIONS[next_step]`. This keeps the dispatch logic centralized and avoids a stale dict that could go out of sync with `MESSAGES`.
- In `src/agents/nodes/confirmation_node.py`: same approach for the 2 strings.
- In `bot/gateway.py:_format_interrupt_value` (lines 151-186): the `f"  {cals} kcal | P: {protein}g..."` line and `Total: ... kcal | ...` line are template strings with multiple placeholders. Make these YAML keys with `{cals}`, `{protein}`, `{carbs}`, `{fat}` placeholders. The `.format(cals=..., protein=..., carbs=..., fat=...)` call replaces the f-string.

### Phase 5: Tests

Cover the loader thoroughly (it is the gatekeeper) and update existing tests that pinned literal English strings.

**Tasks**:
- Create `tests/unit/test_i18n.py` with at minimum:
    - `test_loader_default_language_is_english`
    - `test_loader_picks_hebrew_when_env_var_set` (using `monkeypatch.setenv`)
    - `test_loader_rejects_unsupported_language` (e.g., `BOT_LANGUAGE=fr` raises ValueError)
    - `test_parity_check_passes_when_keysets_match`
    - `test_parity_check_fails_when_he_missing_a_key` (use a tmp dir + `monkeypatch.setattr` to point loader at fixture YAMLs)
    - `test_parity_check_fails_when_en_missing_a_key`
    - `test_parity_check_fails_on_empty_value`
    - `test_parity_check_fails_on_extra_key_not_in_typeddict`
    - `test_placeholder_preservation` — load `MESSAGES["onboarding_complete"]`, format with a name, verify the resulting string contains the name and no `{name}` literal remains.
- Update `tests/unit/test_gateway.py` — every assertion that compares against an English string literal should compare against `gw.MESSAGES["..."]` (or import `MESSAGES` directly). Identify these via grep for `assert_called_once_with("` or `== "` followed by quoted English text inside the test file.
- Update `tests/unit/test_confirmation_node.py` — same treatment for the `_format_batch_preview` test that asserts `"question" in preview` and any string-content assertions.
- Important: the loader runs at import time, so the test module's first import of `src.i18n` validates the real `en.yaml` + `he.yaml`. If those files are broken, every i18n test fails. That's correct behavior — but in tests for the failure cases (parity errors), use a temp directory + `importlib.reload()` so we don't break unrelated test runs. Alternative simpler design: factor `_load_messages` into a pure function that takes file paths as args, then test the function directly against fixture YAMLs without monkeypatching module globals. **Recommended**: do the latter — pure functions are easier to test.

### Phase 6: PRD Update + Docs

Capture the per-user locale backlog item and document the env var for future devs.

**Tasks**:
- Edit `PRD.md` Phase 4 section. Insert (around line 510, after "Routing Style Audit"):
    ```markdown
    - **Per-User Language Preference**: Store a `language` column on `UserProfile` (default `"en"`, allowed values `"en"` / `"he"`). Modify the i18n loader to accept a runtime `lang` parameter alongside the global env-var default, and update the bot/graph to pass each user's stored preference. Enables coaches running a single bot instance with a mix of English- and Hebrew-speaking trainees. Pre-requisite: i18n message extraction (this is the v2 of `docs/plans/i18n-message-extraction.md`).
    ```
- Edit `README.md` — add a short section after "Local Bot Development":
    ```markdown
    ## Localization

    The bot UI language is set via the `BOT_LANGUAGE` env var.
    - Supported: `en` (default), `he`
    - Set on **both** the `langgraph-server` and `fitpal-bot` Railway services — they each load i18n independently, so a mismatch yields half-translated chats.
    - Adding a new string: add the key to `Messages` TypedDict in `src/i18n/__init__.py`, then add the same key to `en.yaml` and `he.yaml`. The startup parity check will refuse to boot if any of the three drift apart.
    ```

### Phase 7: Verification

Make sure nothing breaks at the deploy boundary.

**Tasks**:
- Confirm `.dockerignore` does not exclude `*.yaml` files under `src/i18n/` (otherwise the YAMLs won't be in the Docker image and the loader will crash on container start).
- Run `langgraph dev` locally — the server must start cleanly with default `BOT_LANGUAGE=en`.
- Run `BOT_LANGUAGE=he uv run python -c "from src.i18n import MESSAGES; print(MESSAGES)"` — must succeed and print the (TODO_HE-prefixed) Hebrew dict.
- Run `BOT_LANGUAGE=fr uv run python -c "from src.i18n import MESSAGES"` — must fail with the unsupported-language error.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### 1. ADD pyyaml as direct dependency

- **IMPLEMENT**: Add `pyyaml>=6.0.3` to `[project].dependencies` in `pyproject.toml` via `uv add pyyaml`. This promotes the existing transitive dep to a direct one so we don't break if upstream removes it.
- **PATTERN**: existing `pyproject.toml` lines 7-23.
- **IMPORTS**: N/A — package management.
- **GOTCHA**: Do NOT manually edit `pyproject.toml` — use `uv add pyyaml`. This regenerates `uv.lock` correctly. Manual edits to `pyproject.toml` without re-locking risk environment drift.
- **VALIDATE**: `uv run python -c "import yaml; print(yaml.__version__)"` — must succeed and print the version.

### 2. CREATE src/i18n/ package skeleton

- **IMPLEMENT**: Create directory `src/i18n/` and an empty `src/i18n/__init__.py` (placeholder, will be filled in step 5).
- **PATTERN**: Other packages under `src/` (e.g. `src/services/`, `src/agents/`) — Python packages with `__init__.py`.
- **IMPORTS**: None yet.
- **GOTCHA**: Make sure the directory has no other content; the loader expects exactly `en.yaml`, `he.yaml`, and `__init__.py`.
- **VALIDATE**: `ls src/i18n/` shows only `__init__.py`; `uv run python -c "import src.i18n"` succeeds (empty module).

### 3. CREATE src/i18n/en.yaml

- **IMPLEMENT**: Write all ~22 English strings as a flat YAML mapping. Each key matches a key declared in the `Messages` TypedDict (created in step 4). Keys grouped by prefix: `onboarding_*`, `auth_*`, `error_*`, `confirmation_*`. Strings with placeholders use `{name}`, `{cals}`, `{protein}`, `{carbs}`, `{fat}` exactly as Python `str.format` expects.
- **PATTERN**: see exact strings in `bot/gateway.py` and `src/agents/nodes/confirmation_node.py` (line refs in CONTEXT REFERENCES).
- **IMPORTS**: N/A.
- **GOTCHA**:
    - Use double quotes around string values that contain apostrophes (`"What's your name?"`) — YAML allows single quotes too but doubling-up apostrophes is uglier than just using double quotes.
    - YAML scalar values do not need explicit string typing — `key: "value"` works.
    - Watch for em-dash characters (`—`) in the existing strings (e.g., line 37 of `confirmation_node.py`) — YAML/UTF-8 handles them fine but make sure your editor doesn't auto-convert to a different dash.
    - Do NOT include the `food_name` description format itself (`{food_name} — {amount_g}g{source_tag}`) — that is unit/punctuation, not user copy. Out of scope for v1.
- **VALIDATE**: `uv run python -c "import yaml; d = yaml.safe_load(open('src/i18n/en.yaml')); assert isinstance(d, dict) and len(d) > 15; print(sorted(d.keys()))"` — succeeds and prints all keys.

### 4. CREATE src/i18n/__init__.py — Messages TypedDict + loader

- **IMPLEMENT**: Define the `Messages` TypedDict with exactly the keys you put in `en.yaml`. Implement `_load_yaml(path: Path) -> dict`, `_validate_parity(en: dict, he: dict, expected_keys: set[str]) -> None`, and `_load_messages() -> Messages`. Module-level: `MESSAGES: Messages = _load_messages()`. Use `Path(__file__).parent` to resolve YAML paths. Use `structlog.get_logger(__name__)` for logging. Default `BOT_LANGUAGE="en"`. Supported langs: `("en", "he")`. Use `typing.get_type_hints(Messages).keys()` to derive `EXPECTED_KEYS` at module load.
- **PATTERN**:
    - Env var loading: `src/config.py` lines 28-31.
    - File path resolution: avoid `os.getcwd()`; use `Path(__file__).parent` (memory: prior `BlockingError` incident with `os.getcwd()`).
    - Strict-fail import-time validation: novel pattern in this codebase; document in a one-line comment why.
- **IMPORTS**:
    ```python
    import os
    from pathlib import Path
    from typing import TypedDict, get_type_hints

    import structlog
    import yaml
    ```
- **GOTCHA**:
    - Use `yaml.safe_load`, NOT `yaml.load` — security hardening even though our YAML files are trusted.
    - Collect ALL parity violations into one error, not first-fail. Format: one `ValueError` whose message lists every category of violation that occurred, so Dolev sees the full picture in one boot attempt.
    - Empty-string values count as a parity failure. Document this in the error message: `"key 'X' has empty value in he.yaml — set it or use the English fallback"`.
    - Refactor `_load_messages` so its core logic is a pure function `_load_messages_from_paths(en_path: Path, he_path: Path, lang: str) -> Messages` — this enables the unit tests to call it with fixture paths without mutating module globals.
- **VALIDATE**: `uv run python -c "from src.i18n import MESSAGES; print(len(MESSAGES))"` — must succeed and print the count of keys.

### 5. CREATE src/i18n/he.yaml — Hebrew skeleton

- **IMPLEMENT**: Same key list as `en.yaml`, value = `"TODO_HE: <english value>"` for every key. This satisfies the non-empty-string parity rule while making untranslated keys obvious in any Hebrew bot output.
- **PATTERN**: mirror `en.yaml` from step 3 exactly.
- **IMPORTS**: N/A.
- **GOTCHA**: Keep placeholder syntax (`{name}`, etc.) intact — the parity check doesn't validate placeholders match between EN and HE, but the `.format()` call at runtime will silently produce wrong output if you drop a placeholder. Keeping the EN value as a suffix in the TODO line preserves the placeholder visibly so Dolev sees what to translate.
- **VALIDATE**: `uv run python -c "from src.i18n import MESSAGES; print('OK')"` — must succeed (parity check passes).

### 6. UPDATE bot/gateway.py — replace inline strings with MESSAGES lookups

- **IMPLEMENT**:
    - Add `from src.i18n import MESSAGES` to the imports block (after the existing `noqa: E402` block, since `MESSAGES` triggers the i18n module load which is purely local — no env-var-dependent state beyond `BOT_LANGUAGE`).
    - Delete the `ONBOARDING_QUESTIONS` dict (lines 46-51) and `ONBOARDING_ORDER` (line 52). Keep `ONBOARDING_ORDER` unless it's also used elsewhere — it is just used inside `_handle_onboarding`, so leave it as-is at the top.
    - Add `def _onboarding_question(step: str) -> str: return MESSAGES[f"onboarding_q_{step}"]` after `ONBOARDING_ORDER`.
    - Replace `ONBOARDING_QUESTIONS[next_step]` with `_onboarding_question(next_step)` (lines 241, 395).
    - Replace each remaining literal in the function bodies with the corresponding `MESSAGES[...]` lookup, formatting placeholders via `.format(...)`.
    - Specifically for `_format_interrupt_value` (lines 151-186): replace the f-string macro lines with formatted i18n templates: `MESSAGES["confirmation_macro_line"].format(desc=desc, source_tag=source_tag, cals=cals, protein=protein, carbs=carbs, fat=fat)` and `MESSAGES["confirmation_total_line"].format(...)`.
- **PATTERN**: `MESSAGES["..."]` for static strings; `MESSAGES["..."].format(name=...)` for templates.
- **IMPORTS**: `from src.i18n import MESSAGES`
- **GOTCHA**:
    - `_format_interrupt_value` builds the source tag inline (`source_tag = " (estimated)" if source == "estimated" else ""`). Use `MESSAGES["confirmation_estimated_tag"]` as the tag value when the condition is true. Keep the conditional in the bot code; the i18n only owns the literal.
    - `_format_batch_preview` in `confirmation_node.py` ALSO computes `source_tag` (line 33) for the description string. There is a latent duplication: the description already includes `" (estimated)"` AND `_format_interrupt_value` adds it again. **Out of scope** for this plan — flag it in the report at the end so Dolev can decide whether to clean it up separately. Do not attempt to fix it here.
    - Do not change error log messages or `logger.exception(...)` text — those are not user-facing.
- **VALIDATE**: `uv run pytest tests/unit/test_gateway.py -v` — passes (assertions in those tests will need updating in step 8 first, so this validation actually happens after step 8).

### 7. UPDATE src/agents/nodes/confirmation_node.py — replace 2 strings

- **IMPLEMENT**:
    - Add `from src.i18n import MESSAGES` to imports.
    - Replace `" (estimated)"` (line 33) with `MESSAGES["confirmation_estimated_tag"]`.
    - Replace the question string (line 54) with `MESSAGES["confirmation_question"]`.
- **PATTERN**: same as gateway refactor.
- **IMPORTS**: `from src.i18n import MESSAGES`
- **GOTCHA**: Do not touch the LLM prompt loading (lines 17-26) — `_CONFIRMATION_PROMPT` is for the LLM, not the user.
- **VALIDATE**: `uv run pytest tests/unit/test_confirmation_node.py -v` — passes (assertions need updating in step 8 first).

### 8. UPDATE existing tests to use MESSAGES instead of literal strings

- **IMPLEMENT**:
    - In `tests/unit/test_gateway.py`: every `mock_message.answer.assert_called_once_with("english string here")` becomes `mock_message.answer.assert_called_once_with(gw.MESSAGES["..."])` (after `import bot.gateway as gw` already in the file). Identify all such assertions via `grep -n 'assert_called_once_with("' tests/unit/test_gateway.py` (and same for `assert_called_with`, `assert_any_call`).
    - In `tests/unit/test_confirmation_node.py`: any assertion comparing against `"Please review the following items..."` becomes a comparison against `MESSAGES["confirmation_question"]`.
    - Existing tests that assert on dict structure (`assert "question" in preview`) need NO change.
- **PATTERN**: see `tests/unit/test_gateway.py` lines 67-69 for the existing literal-string assertion.
- **IMPORTS**: tests already import `gw` (alias for `bot.gateway`). For `test_confirmation_node.py`, add `from src.i18n import MESSAGES`.
- **GOTCHA**: Do not over-refactor. Only change assertions that compare against the localized strings — leave structural and behavioral assertions alone.
- **VALIDATE**: `uv run pytest tests/unit/test_gateway.py tests/unit/test_confirmation_node.py -v` — all pass.

### 9. CREATE tests/unit/test_i18n.py

- **IMPLEMENT**: New file with file-level docstring (Scope: i18n loader and parity check; LLM Usage: NONE). Class-grouped tests covering: env var resolution (default, supported, unsupported), parity check (success, missing keys, extra keys, empty values), placeholder preservation. For failure-mode tests, build small fixture dicts in-test and call the pure `_load_messages_from_paths(...)` function — do NOT rely on writing real YAML files unless absolutely necessary.
- **PATTERN**: see `tests/unit/test_gateway.py` for header docstring style and `tests/unit/test_confirmation_node.py` for class-based grouping.
- **IMPORTS**:
    ```python
    import pytest

    from src.i18n import MESSAGES, Messages, _validate_parity, _load_messages_from_paths
    ```
- **GOTCHA**:
    - `_load_messages_from_paths` is the pure function from step 4. If you skipped extracting it: you'll have to rely on `monkeypatch.setattr` to swap module-level paths, which is messier. Strong recommendation: refactor to pure function in step 4.
    - For tests that need to write fixture YAMLs to disk, use `tmp_path` pytest fixture — never write into the real `src/i18n/` directory.
    - Test `BOT_LANGUAGE` env var via `monkeypatch.setenv`/`monkeypatch.delenv`, not `os.environ` mutation.
- **VALIDATE**: `uv run pytest tests/unit/test_i18n.py -v` — all pass.

### 10. UPDATE PRD.md — backlog per-user locale

- **IMPLEMENT**: Insert the bullet specified in Phase 6 of IMPLEMENTATION PLAN, around line 510 of `PRD.md` (after the "Routing Style Audit" item, before the "HITL Confirmation: Add-Item Edit Type" item).
- **PATTERN**: existing Phase 4 bullets at lines 494-512 — same prose style, same level of detail.
- **IMPORTS**: N/A (Markdown).
- **GOTCHA**: Use the `⏳` marker (or no marker for new items) consistent with surrounding bullets. Do not use `✅` — this is not yet done.
- **VALIDATE**: `grep -n "Per-User Language Preference" PRD.md` — returns the inserted line.

### 11. UPDATE README.md — document BOT_LANGUAGE

- **IMPLEMENT**: Add the "Localization" section as specified in Phase 6 of IMPLEMENTATION PLAN, placed after the existing "Local Bot Development" block.
- **PATTERN**: existing README sections (`## Quickstart`, `## Local Bot Development`, etc.) — match heading level and tone.
- **IMPORTS**: N/A (Markdown).
- **VALIDATE**: `grep -n "BOT_LANGUAGE" README.md` — returns the documented line.

### 12. VERIFY .dockerignore does not exclude i18n YAMLs

- **IMPLEMENT**: Read `.dockerignore`. Confirm there is no `*.yaml` or `src/i18n/*.yaml` exclusion. If there is, add an exception (`!src/i18n/*.yaml`).
- **PATTERN**: standard `.dockerignore` syntax.
- **IMPORTS**: N/A.
- **VALIDATE**: `cat .dockerignore` (manual inspection).

### 13. RUN full validation suite

- **IMPLEMENT**: Execute the validation commands listed below in order. Fix anything that fails before declaring done.
- **VALIDATE**: see VALIDATION COMMANDS section.

---

## TESTING STRATEGY

### Unit Tests (`tests/unit/test_i18n.py`)

Cover the loader exhaustively because it is the gatekeeper for the entire feature:

- **Loader env var resolution**: default to `en`, accept `he`, reject anything else with a clear error (`ValueError` mentioning "BOT_LANGUAGE" and the unsupported value).
- **Parity check — success**: when EN and HE have identical key sets matching the TypedDict, `_validate_parity` returns without raising.
- **Parity check — missing key in HE**: `ValueError` with the missing key name.
- **Parity check — missing key in EN**: same.
- **Parity check — extra key in EN not in TypedDict**: same.
- **Parity check — extra key in HE not in TypedDict**: same.
- **Parity check — empty value**: `ValueError` mentioning the empty key and the language file.
- **Parity check — multiple violations reported together**: when both EN and HE have missing keys plus an empty value, all three violations appear in the same error message.
- **Placeholder preservation**: `MESSAGES["onboarding_complete"].format(name="Dolev")` produces a string containing "Dolev" and no `{name}` literal.

### Updated Existing Tests

`tests/unit/test_gateway.py` and `tests/unit/test_confirmation_node.py` need the literal-string assertions replaced with `MESSAGES[...]` lookups — see step 8.

### Integration Tests

No new integration tests required. The i18n loader is pure (no DB, no network) and is fully covered by unit tests. Existing graph-api and integration tests will exercise the i18n module indirectly via the bot/node imports — if the loader is broken, those tests fail at collection time.

### Edge Cases

- `BOT_LANGUAGE=EN` (uppercase) — loader lowercases via `.lower()`. Must work.
- `BOT_LANGUAGE=` (empty string) — loader `.lower()` returns `""`, which is not in `SUPPORTED_LANGS`, so it raises. Acceptable: an explicitly-empty env var should fail loud, not silently default. (If we want it to default, the check needs to come before the validation.) **Decision**: explicitly empty string → raise (forces operators to either set a real value or unset the var).
- Missing YAML file (e.g., `he.yaml` deleted) — `_load_yaml` raises `FileNotFoundError`. Acceptable.
- YAML syntax error — `yaml.safe_load` raises `yaml.YAMLError`. Acceptable.
- Hebrew RTL rendering in Telegram — Telegram handles UTF-8 and RTL natively. No code change needed; this is a manual-test concern.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

```bash
uv run ruff check src/i18n/ bot/gateway.py src/agents/nodes/confirmation_node.py tests/unit/test_i18n.py
```

### Level 2: Unit Tests (full suite)

```bash
uv run pytest tests/unit/ -v
```

Specifically these files:
```bash
uv run pytest tests/unit/test_i18n.py tests/unit/test_gateway.py tests/unit/test_confirmation_node.py -v
```

### Level 3: Integration / Graph-API

These should not regress. If they do, the i18n loader broke something at module import:
```bash
uv run pytest tests/integration/ -v
```

(Optional, if changing graph-touching code further:)
```bash
uv run pytest tests/graph_api/ -v -s
```

### Level 4: Manual Validation

1. **Default English boot**:
   ```bash
   uv run python -c "from src.i18n import MESSAGES; print('OK', len(MESSAGES))"
   ```
   Must print `OK <count>`.

2. **Hebrew boot (TODO_HE-prefixed)**:
   ```bash
   BOT_LANGUAGE=he uv run python -c "from src.i18n import MESSAGES; print(MESSAGES['onboarding_welcome'])"
   ```
   Must print the Hebrew skeleton string starting with `TODO_HE:`.

3. **Unsupported language fails**:
   ```bash
   BOT_LANGUAGE=fr uv run python -c "from src.i18n import MESSAGES" 2>&1 | grep -i "unsupported"
   ```
   Must produce a clear error mentioning "BOT_LANGUAGE" and "fr".

4. **Studio dev server starts**:
   ```bash
   uv run langgraph dev
   ```
   Server must boot cleanly (no errors). Visit http://127.0.0.1:2024 — confirm graph visualizes normally.

5. **Local bot smoke test (English)** — run `uv run python -m bot.gateway` with `POLLING_MODE=true` against your dev Telegram bot, send a message, verify the bot replies with the same English copy as before this change.

6. **Local bot smoke test (Hebrew skeleton)** — set `BOT_LANGUAGE=he` in `.env`, restart the bot, send a message. Verify replies appear with the `TODO_HE:` prefix (proves the loader picks `he.yaml`). Do NOT deploy this state — it's a sanity check.

---

## ACCEPTANCE CRITERIA

- [ ] `src/i18n/` package exists with `__init__.py`, `en.yaml`, `he.yaml`.
- [ ] `Messages` TypedDict declares every user-facing string key the system needs.
- [ ] `en.yaml` is fully populated; bot behavior in English is byte-identical to pre-refactor (verified by passing `tests/unit/test_gateway.py`).
- [ ] `he.yaml` is a parity skeleton with `TODO_HE:`-prefixed values for every key.
- [ ] Loader fails fast at module-import time on any parity violation — never silently falls back.
- [ ] `BOT_LANGUAGE` env var: `en` (default), `he`, anything else raises `ValueError`.
- [ ] All existing unit tests still pass after assertions are updated.
- [ ] New `tests/unit/test_i18n.py` covers all scenarios listed in TESTING STRATEGY.
- [ ] `pyyaml` appears as a direct dep in `pyproject.toml`.
- [ ] PRD `Phase 4` has a new pending bullet for "Per-User Language Preference".
- [ ] README has a "Localization" section documenting `BOT_LANGUAGE`.
- [ ] `.dockerignore` does not exclude `src/i18n/*.yaml`.
- [ ] `langgraph dev` starts without errors.
- [ ] Manual bot test (EN): bot responds with same strings as before.
- [ ] Manual bot test (HE): bot responds with `TODO_HE:` prefixed strings (proving env-var-driven file selection works).

---

## COMPLETION CHECKLIST

- [ ] All tasks 1–13 completed in order.
- [ ] Each task validation passed immediately.
- [ ] All Level-1 through Level-4 validation commands executed successfully.
- [ ] `uv run pytest tests/unit/ -v` passes (no regressions).
- [ ] `uv run pytest tests/integration/ -v` passes.
- [ ] No linting errors from `uv run ruff check`.
- [ ] Manual EN and HE-skeleton bot tests confirm feature works end-to-end.
- [ ] Acceptance criteria all met.
- [ ] Code reviewed for quality and adherence to project patterns.

---

## NOTES

### Out of scope (intentional)

1. **LLM-generated coach responses** — `prompts/response_generator.md` line 20 already instructs the model to match the user's language. No change needed in `response_node`. If user types Hebrew, GPT-4.1-nano replies in Hebrew. The bot's wrappers (welcome, errors, HITL labels) are what this plan covers — the actual conversation is handled by the LLM.

2. **System prompts in `prompts/*.md`** — these are LLM instructions, not user copy. They stay in English; the LLM translates its output as needed.

3. **Per-user locale** — backlogged in PRD Phase 4 as a v2 of this work. Adds `UserProfile.language` column and per-call language selection.

4. **Latent bug in `_format_interrupt_value`** — the `(estimated)` tag may be applied twice (once by `_format_batch_preview` baking it into `description`, once by the bot rendering loop). Out of scope; flag for separate cleanup.

5. **Non-localized "g" / em-dash / numeric formatting** — `f"{food_name} — {amount_g}g{source_tag}"` in `confirmation_node.py:37` mixes data and copy. The "g" suffix and em-dash separator are language-neutral enough to leave alone for v1. Worth revisiting if a localization audit later finds Hebrew users complaining.

### Cross-process env-var requirement

Both `langgraph-server` and `fitpal-bot` Railway services import `src/i18n/`. They each load `BOT_LANGUAGE` independently. If you set `BOT_LANGUAGE=he` on only one, you get a half-translated bot (Hebrew labels from the bot, English question text from the graph node — or vice versa). When deploying the Hebrew flip, **set the env var on both services in the same Railway deploy**. Documented in README.

### Risks

- **Risk**: A future contributor adds a new user-facing string in code without going through i18n. Mitigation: add a `ruff` rule or pre-commit hook that flags hardcoded English in `bot/` and `src/agents/nodes/`. Not required for this plan but worth a follow-up backlog item.
- **Risk**: The strict parity check on import time means a busted `he.yaml` makes the whole server unbootable. Mitigation: `TODO_HE:` placeholder values keep the file shape valid; only deletion of a key is fatal. CI will catch it.
- **Risk**: Race between adding a TypedDict key and updating both YAMLs. Mitigation: parity check immediately fails with the specific missing key name. Loud, fast feedback. The new `test_i18n.py` parity tests run in CI on every push.

### Confidence

8/10 for one-pass implementation success. The string surface is well-bounded, the loader pattern is straightforward, and tests are already conventionalized. The two unknowns: (1) whether `_format_interrupt_value` reformatting introduces any subtle string-formatting bug across the bot↔graph boundary; (2) whether refactoring `ONBOARDING_QUESTIONS` to a function changes any test that imports it directly. Both are addressable with normal test-driven work.
