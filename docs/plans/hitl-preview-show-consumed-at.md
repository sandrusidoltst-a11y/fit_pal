# Feature: HITL preview shows `consumed_at` date (UX Fix #5)

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files.

> **Branch**: `ux/hitl-preview-date-and-natural-units` (already created from `main`).
>
> **Scope of THIS plan**: Fix #5 only — the date label. Fix #4 (natural-unit rendering) is a separate follow-up plan/PR on the same branch.
>
> **Commit policy**: One atomic commit on this branch — `ux(hitl): show consumed_at date in confirmation preview`. Validation gate (unit tests) must pass before commit.

## Feature Description

When a user logs a meal with a date qualifier — e.g., *"אתמול אכלתי 100 גרם חזה עוף"* ("yesterday I ate 100g chicken breast") — the HITL confirmation preview currently shows the food, amount, macros, servings, and category but **no date**. The user has no signal about what date the bot has routed the log to before confirming. Bot may extract the date correctly (and write the row correctly), but the missing preview means the user is asked to confirm a payload they cannot fully verify.

This fix surfaces the routing date in the preview so the user can verify *before* confirming.

## User Story

As a **FitPal user logging a meal with a date qualifier**,
I want to **see the target date on the confirmation preview**,
So that **I can catch a date-extraction mistake before saying "yes" and committing the log to the wrong day**.

## Problem Statement

Run `tests/ux-loop/log-yesterday-and-today-then-query/runs/run1-baseline/` (T1: *"אתמול אכלתי 100 גרם חזה עוף"*) captured this raw interrupt payload:

```json
{
  "question": "רגע, בוא נוודא שתפסתי נכון לפני שאני שומר:",
  "items": [
    {
      "index": 0,
      "description": "חזה עוף — 100.0g",
      "calories": 120.0,
      "protein": 22.0,
      "carbs": 0.0,
      "fat": 2.6,
      "source": "database",
      "servings": 1.0,
      "category": "protein"
    }
  ],
  "totals": { "calories": 120.0, "protein": 22.0, "carbs": 0.0, "fat": 2.6 }
}
```

`consumed_at` is set in `state["log_food"]["consumed_at"]` (the DB write actually lands on yesterday at noon — verified via `db-snapshot.md` for the same run), but the preview payload doesn't expose it. `_format_batch_preview` in `confirmation_node.py` doesn't even receive the state, so it has no chance to surface the date.

This is purely a **preview-rendering bug**, not a date-extraction or routing bug.

## Solution Statement

Two-side change with one atomic commit:

1. **Graph side** (`src/agents/nodes/confirmation_node.py`):
   - Extend `_format_batch_preview(items, consumed_at=None)` to accept the optional date.
   - Add a top-level `consumed_at` field (ISO date string `"YYYY-MM-DD"` or `None`) to the returned payload.
   - Both call sites in `confirmation_node` pass `state.get("log_food", {}).get("consumed_at")`.

2. **Gateway side** (`bot/gateway.py`):
   - Add a `_format_date_label(iso_date: str) -> str | None` helper that converts an ISO date to a localized label by comparing to *today in Israel local* (`USER_TIMEZONE`):
     - Today → `confirmation_date_today` ("היום" / "today")
     - Yesterday → `confirmation_date_yesterday` ("אתמול" / "yesterday")
     - Other → `confirmation_date_other` formatted as `{day}.{month}` (he) / `{month}/{day}` (en)
   - Wrap with `confirmation_date_for` template (`"📅 ל{date_label}"` he / `"📅 for {date_label}"` en).
   - In `_format_interrupt_value`, append the date line **right after the question, before the item blocks** when `consumed_at` is present. Missing field → skip the line (back-compat for in-flight checkpoint state).

Always render when `consumed_at` is set, including today (consistency over terseness; `consumed_at` is `None` for the default "no date qualifier" case anyway, so "today" only appears when the user explicitly said so or the input parser inferred it).

Date format for "other" dates: short `D.M` (Hebrew) / `M/D` (English) — no year. Cross-year is rare for food logs and we'll re-evaluate if it ever surfaces.

## Feature Metadata

**Feature Type**: Bug Fix (UX gap — preview rendering)
**Estimated Complexity**: Low — one signature change, one new payload field, one gateway helper, four new i18n keys per language.
**Primary Systems Affected**:
- `src/agents/nodes/confirmation_node.py` (`_format_batch_preview` + caller)
- `bot/gateway.py` (`_format_interrupt_value`)
- `src/i18n/__init__.py` (`Messages` TypedDict + new keys)
- `src/i18n/en.yaml` + `src/i18n/he.yaml` (new key values)

**Dependencies**: None. Stdlib only (`datetime`, `zoneinfo` already imported via `src.config.USER_TIMEZONE`).

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: YOU MUST READ THESE BEFORE IMPLEMENTING

- `src/agents/nodes/confirmation_node.py` (lines 30-73) — current `_format_batch_preview` shape; the payload dict we extend.
- `src/agents/nodes/confirmation_node.py` (lines 76-144) — `confirmation_node` body, both call sites of `_format_batch_preview` (initial + post-edit re-render).
- `src/agents/state.py` (lines 89-94) — `LogFoodSubState` defines `consumed_at: Optional[datetime]`.
- `src/agents/nodes/response_node.py` (lines 164-172) — **important precedent**: `consumed_at` may arrive as either `datetime` or `str` (LangGraph state serialization). Mirror the `isinstance(consumed_at, datetime)` defensive check.
- `bot/gateway.py` (lines 159-207) — `_format_interrupt_value` current rendering pipeline (`question` → items → totals → reply_hint).
- `src/config.py` (lines 22-35) — `USER_TIMEZONE = ZoneInfo("Asia/Jerusalem")` is the source of truth for "today" comparisons. Re-use, do not redefine.
- `src/i18n/__init__.py` (lines 33-67) — `Messages` TypedDict; **i18n parity check at import time refuses to boot on drift between TypedDict and YAML files**. Adding any new key requires updating all three files (TypedDict + en.yaml + he.yaml) atomically.
- `src/i18n/en.yaml` + `src/i18n/he.yaml` (HITL section ~line 35-50) — existing confirmation keys; mirror placement for new keys.
- `tests/unit/test_confirmation_node.py` (lines 23-138) — `SAMPLE_BATCH` fixture + `TestFormatBatchPreview` class; extend with new tests.
- `tests/unit/test_gateway.py` — currently mocks `_get_interrupt_state` so the formatter isn't directly exercised; add a new `TestFormatInterruptValue` class.
- `tests/ux-loop/log-yesterday-and-today-then-query/runs/run1-baseline/handoffs/hitl-preview-missing-date.md` — original handoff record with raw payload evidence.

### New Files to Create

None — all changes are edits to existing files.

### Relevant Documentation — read before implementing

- LangGraph state checkpointing serializes/deserializes state through JSON. `datetime` fields can come back as ISO strings on a resumed run. The defensive check in `response_node.py:170` (`isinstance(consumed_at, datetime)`) is the codebase's established pattern — apply the same.
- LangGraph `interrupt()` value is part of state and goes through the same serialization. The gateway reads the interrupt value from the HTTP API (`/threads/{id}/state`), so the payload **is JSON** by the time it reaches `_format_interrupt_value`. The top-level `consumed_at` field will arrive as a string regardless of how the graph wrote it — but the graph still needs to emit a JSON-safe value. ISO date string is the safest.

### Patterns to Follow

**Defensive consumed_at handling** (from `src/agents/nodes/response_node.py:166-171`):
```python
consumed_at = log_food.get("consumed_at")
if consumed_at:
    context["consumed_at"] = (
        consumed_at.isoformat()
        if isinstance(consumed_at, datetime)
        else str(consumed_at)
    )
```

**i18n template usage** (from `bot/gateway.py:178`):
```python
MESSAGES["confirmation_macro_line"].format(
    cals=cals, protein=protein, carbs=carbs, fat=fat
)
```

**Sections-list rendering pattern** (from `bot/gateway.py:159-207`):
- Build `sections: list[str]`
- Append each block conditionally
- Join with `"\n\n"` at the end

Insert the new date section **between `question` and `item_blocks`** so the user reads "Let me confirm: → 📅 for yesterday → [items]" — the date frames what follows.

**Test fixture pattern** (from `tests/unit/test_confirmation_node.py:23`):
- `SAMPLE_BATCH` is a module-level constant
- Each test calls `_format_batch_preview(SAMPLE_BATCH)` and asserts on the returned dict

---

## IMPLEMENTATION PLAN

### Phase 1: i18n Foundation

Add the new keys first because the parity check would block the rest of the work otherwise. Three files must change in lockstep: `Messages` TypedDict, `en.yaml`, `he.yaml`.

**Tasks:**
- Add 4 new keys to `Messages` TypedDict.
- Add 4 new key/value pairs to `en.yaml`.
- Add 4 new key/value pairs to `he.yaml`.
- Boot-check: `python -c "from src.i18n import MESSAGES; print(MESSAGES['confirmation_date_for'])"` should print without raising the parity error.

### Phase 2: Graph-Side Payload

Extend `_format_batch_preview` and update its two call sites in the same node. No edits to other nodes.

**Tasks:**
- Update `_format_batch_preview` signature to accept `consumed_at: datetime | str | None = None`.
- Compute `consumed_at_iso` defensively (handle both datetime and pre-serialized string), extract date portion only.
- Add `"consumed_at": consumed_at_iso` to the returned payload (None when not present).
- Update both call sites in `confirmation_node` to pass `state.get("log_food", {}).get("consumed_at")`.

### Phase 3: Gateway-Side Rendering

Add `_format_date_label` helper and call it in `_format_interrupt_value`. No changes to other gateway functions.

**Tasks:**
- Import `date` from `datetime` and `USER_TIMEZONE` from `src.config` in `bot/gateway.py` (verify these aren't already imported).
- Add module-level `_format_date_label(iso_date: str) -> str | None` helper.
- In `_format_interrupt_value`, after the `question` section, conditionally append the formatted date label using the helper.

### Phase 4: Tests & Validation

Cover both the graph-side payload shape and the gateway-side rendering. Use real `datetime.now(USER_TIMEZONE)` for "today/yesterday" assertions (no time-freezing — overkill).

**Tasks:**
- Extend `TestFormatBatchPreview` with three cases: `consumed_at=None`, `consumed_at=<datetime>`, `consumed_at=<iso string>`.
- Add `TestFormatInterruptValue` class to `test_gateway.py` with six cases covering missing/None/today/yesterday/older/malformed.
- Run unit suite end-to-end.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### 1. UPDATE `src/i18n/__init__.py`

- **IMPLEMENT**: Add 4 new fields to the `Messages` TypedDict, in the "HITL confirmation render (bot)" group:
  ```python
  # HITL date label (bot-rendered when consumed_at is set)
  confirmation_date_for: str
  confirmation_date_today: str
  confirmation_date_yesterday: str
  confirmation_date_other: str
  ```
- **PATTERN**: Existing groups in `Messages` (line 33-67) are tagged with comments — mirror the style.
- **IMPORTS**: None new.
- **GOTCHA**: `EXPECTED_KEYS` is derived via `get_type_hints(Messages)` at module import time (line 71). The parity check (`_load_yaml` + comparison) runs immediately. If you update the TypedDict but forget either YAML, every import of `src.i18n` will raise — including the test suite.
- **VALIDATE**: After this task alone, `uv run python -c "from src.i18n import MESSAGES"` should **fail** with a parity error (we haven't updated the YAMLs yet). That's expected and correct — confirms the check is live.

### 2. UPDATE `src/i18n/en.yaml`

- **IMPLEMENT**: Add a new section with 4 keys, placed under the existing "HITL confirmation render (bot)" group (after `confirmation_reply_hint`):
  ```yaml
  # --- HITL date label (bot-rendered when consumed_at is set) ---
  confirmation_date_for: "📅 for {date_label}"
  confirmation_date_today: "today"
  confirmation_date_yesterday: "yesterday"
  confirmation_date_other: "{month}/{day}"
  ```
- **PATTERN**: Mirror existing section comment + key spacing.
- **IMPORTS**: N/A (YAML).
- **GOTCHA**: `confirmation_date_other` uses `{month}` and `{day}` placeholders that the gateway helper will fill via `.format(month=..., day=...)`. Keep the placeholder names exact.
- **VALIDATE**: After this task `MESSAGES` import will still fail (he.yaml missing the keys). Don't run the validate command yet; it'll error.

### 3. UPDATE `src/i18n/he.yaml`

- **IMPLEMENT**: Add the same 4 keys under the same section:
  ```yaml
  # --- HITL date label (bot-rendered when consumed_at is set) ---
  confirmation_date_for: "📅 ל{date_label}"
  confirmation_date_today: "היום"
  confirmation_date_yesterday: "אתמול"
  confirmation_date_other: "{day}.{month}"
  ```
- **PATTERN**: Hebrew dates use day-first format (D.M) by convention; English uses month-first (M/D).
- **IMPORTS**: N/A (YAML).
- **GOTCHA**: The Hebrew `confirmation_date_for` value embeds the label without a space because Hebrew prefixes "ל" (lamed) directly to nouns ("ל-אתמול" → "לאתמול"). Don't add a space before `{date_label}`.
- **VALIDATE**:
  - `uv run python -c "from src.i18n import MESSAGES; print(MESSAGES['confirmation_date_for'])"` → prints `📅 for {date_label}` (en is default).
  - `BOT_LANGUAGE=he uv run python -c "from src.i18n import MESSAGES; print(MESSAGES['confirmation_date_for'])"` → prints `📅 ל{date_label}`.

### 4. UPDATE `src/agents/nodes/confirmation_node.py` — `_format_batch_preview` signature + payload

- **IMPLEMENT**:
  - Add `from datetime import datetime` at the top of the file (if not already imported — currently it's not).
  - Change signature: `def _format_batch_preview(items: list[MacroResult], consumed_at: datetime | str | None = None) -> dict:`.
  - Inside the function, before the `return` statement, compute the ISO date defensively:
    ```python
    consumed_at_iso: str | None = None
    if consumed_at is not None:
        if isinstance(consumed_at, datetime):
            consumed_at_iso = consumed_at.date().isoformat()
        else:
            # Already serialized (LangGraph state round-trip) — take date portion.
            consumed_at_iso = str(consumed_at)[:10]
    ```
  - Add `"consumed_at": consumed_at_iso,` as a new top-level key in the returned dict (between `"items"` and `"totals"` for readability, but order doesn't affect behavior).
- **PATTERN**: Defensive-handling pattern from `src/agents/nodes/response_node.py:166-171`.
- **IMPORTS**: `from datetime import datetime` (new).
- **GOTCHA**:
  - `str(consumed_at)[:10]` works because ISO datetime strings start with `YYYY-MM-DD`. If `consumed_at` arrives as something exotic (e.g., a `date` object), `[:10]` still grabs the date portion. If it's malformed, the gateway's date-parsing will catch it and fall back to skipping the line — see Task 6 for the helper's error handling.
  - Don't try to `datetime.fromisoformat` and re-format; the round-trip can drop timezone info and confuse `.date()`. Defensive substring is sufficient and correct.
- **VALIDATE**: `uv run python -c "from src.agents.nodes.confirmation_node import _format_batch_preview; from datetime import datetime; print(_format_batch_preview([], consumed_at=datetime(2026,5,7,12)))"` → printed dict has `'consumed_at': '2026-05-07'`.

### 5. UPDATE `src/agents/nodes/confirmation_node.py` — pass `consumed_at` from both call sites

- **IMPLEMENT**: Two call sites in `confirmation_node` body need the date passed in.
  - Initial preview (currently line ~93): change
    ```python
    preview = _format_batch_preview(batch)
    ```
    to
    ```python
    consumed_at = state.get("log_food", {}).get("consumed_at")
    preview = _format_batch_preview(batch, consumed_at)
    ```
  - Post-edit re-render (currently line ~143): change
    ```python
    preview = _format_batch_preview(batch)
    ```
    to
    ```python
    preview = _format_batch_preview(batch, consumed_at)
    ```
    (reuses the variable from the same scope — `consumed_at` is computed once at the top of the function and reused per loop iteration, since the date doesn't change during edits).
- **PATTERN**: `state.get("log_food", {}).get("consumed_at")` mirrors how `commit_node.py:30` and `response_node.py:166` read the same field defensively.
- **IMPORTS**: None new.
- **GOTCHA**: `state["log_food"]` may legitimately be `{}` (input parser writes `{}` for non-LOG_FOOD actions per the discriminated-state refactor — see commit_logs/2026-05-06_refactor-discriminated-action-state.md). The `.get("log_food", {})` guard handles that.
- **VALIDATE**: `uv run pytest tests/unit/test_confirmation_node.py -v` — existing tests must still pass (the new positional arg is keyword-defaulted to `None`, so old callers in tests don't break).

### 6. UPDATE `bot/gateway.py` — add `_format_date_label` helper

- **IMPLEMENT**: Add module-level helper above `_format_interrupt_value`:
  ```python
  from datetime import date, datetime, timedelta, timezone  # 'date' may need adding
  from src.config import USER_TIMEZONE  # may need adding


  def _format_date_label(iso_date: str) -> str | None:
      """Format an ISO date string ('YYYY-MM-DD') as a localized label.

      Returns 'today' / 'yesterday' / '{day}.{month}' (he) or '{month}/{day}' (en),
      wrapped by the confirmation_date_for template. Returns None on parse failure
      so the caller can skip rendering rather than crash.
      """
      try:
          target = date.fromisoformat(iso_date)
      except (TypeError, ValueError):
          return None

      today_local = datetime.now(USER_TIMEZONE).date()
      delta_days = (today_local - target).days

      if delta_days == 0:
          label = MESSAGES["confirmation_date_today"]
      elif delta_days == 1:
          label = MESSAGES["confirmation_date_yesterday"]
      else:
          label = MESSAGES["confirmation_date_other"].format(
              day=target.day, month=target.month
          )

      return MESSAGES["confirmation_date_for"].format(date_label=label)
  ```
- **PATTERN**: i18n template usage matches existing `bot/gateway.py:178`. Israel-local "today" comparison matches `src/agents/nodes/stats_node.py` post-PR-#26 fix.
- **IMPORTS**:
  - Verify `date` is in the existing `from datetime import ...` line (gateway already imports `datetime, timedelta, timezone` per `tests/unit/test_gateway.py:11` precedent — add `date` if missing).
  - Add `from src.config import USER_TIMEZONE` if not already imported (grep the file first).
- **GOTCHA**:
  - Compute "today" inside the helper (not at module load) so the comparison reflects request time, not server start time. Matters for long-lived bot processes that span midnight.
  - Future dates (`delta_days < 0`) fall through to the `else` branch and render as a date — that's the right behavior for edge cases like "log breakfast for tomorrow morning" which the input parser may eventually support.
  - Returning `None` on parse failure is intentional: the caller skips rendering. Don't raise — a malformed date in the payload should not crash the confirmation flow.
- **VALIDATE**: Inline import test — `uv run python -c "from bot.gateway import _format_date_label; print(_format_date_label('2026-05-07'))"` should print a string starting with 📅.

### 7. UPDATE `bot/gateway.py` — `_format_interrupt_value` renders the date line

- **IMPLEMENT**: After the `question` block (current lines 163-165), insert:
  ```python
  consumed_at_iso = value.get("consumed_at")
  if consumed_at_iso:
      date_line = _format_date_label(consumed_at_iso)
      if date_line:
          sections.append(date_line)
  ```
- **PATTERN**: Mirror the existing conditional-section pattern (e.g., `if totals:` block at line 194-203).
- **IMPORTS**: None new (helper is in the same module).
- **GOTCHA**:
  - Two-level guard: outer `if consumed_at_iso:` skips when the field is absent or `None` (back-compat for in-flight checkpoint state from before this fix); inner `if date_line:` skips when parsing fails.
  - Position matters: the date should render **between** the question and the items, not after totals. The user reads "Let me confirm: → 📅 for yesterday → [items] → totals" — this framing is the whole point of the fix.
- **VALIDATE**: Covered by Task 9 below.

### 8. UPDATE `tests/unit/test_confirmation_node.py` — extend `TestFormatBatchPreview`

- **IMPLEMENT**: Add three new test methods to the `TestFormatBatchPreview` class:
  ```python
  def test_consumed_at_default_none(self):
      """
      arrange: sample batch, no consumed_at passed (default).
      act:     format batch preview.
      assert:  payload has 'consumed_at' key set to None.
      """
      preview = _format_batch_preview(SAMPLE_BATCH)
      assert "consumed_at" in preview
      assert preview["consumed_at"] is None

  def test_consumed_at_datetime_serializes_to_iso_date(self):
      """
      arrange: sample batch + a datetime for consumed_at.
      act:     format batch preview with the datetime.
      assert:  payload's consumed_at is the ISO date string (date portion only).
      """
      from datetime import datetime, timezone
      ts = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
      preview = _format_batch_preview(SAMPLE_BATCH, consumed_at=ts)
      assert preview["consumed_at"] == "2026-05-07"

  def test_consumed_at_pre_serialized_string_passes_through(self):
      """
      arrange: consumed_at arriving as an ISO string (LangGraph state round-trip).
      act:     format batch preview with the string.
      assert:  payload's consumed_at is the date portion of the string.
      """
      preview = _format_batch_preview(SAMPLE_BATCH, consumed_at="2026-05-07T12:00:00+00:00")
      assert preview["consumed_at"] == "2026-05-07"
  ```
- **PATTERN**: Mirror existing `TestFormatBatchPreview` style — AAA docstring, module-level `SAMPLE_BATCH` reuse.
- **IMPORTS**: Inline `from datetime import datetime, timezone` inside test bodies — match existing test-file style (no top-of-file changes).
- **GOTCHA**: Don't pin `datetime.now()` here — these tests are deterministic (no "today" comparison in the graph helper; that lives in the gateway).
- **VALIDATE**: `uv run pytest tests/unit/test_confirmation_node.py::TestFormatBatchPreview -v` → all 8 tests pass (5 existing + 3 new).

### 9. UPDATE `tests/unit/test_gateway.py` — add `TestFormatInterruptValue`

- **IMPLEMENT**: Add a new test class after `TestHITLFlow`:
  ```python
  class TestFormatInterruptValue:
      """Tests for the HITL interrupt-value → user-text formatter."""

      def _base_payload(self, consumed_at_iso: str | None = None) -> dict:
          payload = {
              "question": "Confirm:",
              "items": [
                  {
                      "description": "chicken — 200g",
                      "calories": 330, "protein": 62, "carbs": 0, "fat": 7.2,
                      "servings": None, "category": None,
                  }
              ],
              "totals": {"calories": 330, "protein": 62, "carbs": 0, "fat": 7.2},
          }
          if consumed_at_iso is not None:
              payload["consumed_at"] = consumed_at_iso
          return payload

      def test_omits_date_line_when_consumed_at_missing(self):
          """
          arrange: payload without consumed_at field (back-compat).
          act:     format interrupt value.
          assert:  no '📅' in output.
          """
          out = gw._format_interrupt_value(self._base_payload())
          assert "📅" not in out

      def test_omits_date_line_when_consumed_at_none(self):
          """
          arrange: payload with consumed_at explicitly None.
          act:     format interrupt value.
          assert:  no '📅' in output.
          """
          out = gw._format_interrupt_value(self._base_payload(consumed_at_iso=None))
          assert "📅" not in out

      def test_renders_today_label(self):
          """
          arrange: consumed_at = today in Israel local.
          act:     format interrupt value.
          assert:  output contains the localized today label.
          """
          from datetime import datetime
          from src.config import USER_TIMEZONE
          today_iso = datetime.now(USER_TIMEZONE).date().isoformat()
          out = gw._format_interrupt_value(self._base_payload(today_iso))
          assert gw.MESSAGES["confirmation_date_today"] in out
          assert "📅" in out

      def test_renders_yesterday_label(self):
          """
          arrange: consumed_at = yesterday in Israel local.
          act:     format interrupt value.
          assert:  output contains the localized yesterday label.
          """
          from datetime import datetime, timedelta
          from src.config import USER_TIMEZONE
          yday = (datetime.now(USER_TIMEZONE).date() - timedelta(days=1)).isoformat()
          out = gw._format_interrupt_value(self._base_payload(yday))
          assert gw.MESSAGES["confirmation_date_yesterday"] in out

      def test_renders_short_date_for_older(self):
          """
          arrange: consumed_at = a fixed older date.
          act:     format interrupt value.
          assert:  output contains a D.M / M/D rendering of the date.
          """
          out = gw._format_interrupt_value(self._base_payload("2026-01-15"))
          # Either '15.1' (he) or '1/15' (en) depending on BOT_LANGUAGE; check both.
          assert ("15.1" in out) or ("1/15" in out)
          assert "📅" in out

      def test_malformed_date_skips_line_without_crash(self):
          """
          arrange: consumed_at is a non-ISO string.
          act:     format interrupt value.
          assert:  no '📅' in output, no exception raised.
          """
          out = gw._format_interrupt_value(self._base_payload("not-a-date"))
          assert "📅" not in out
  ```
- **PATTERN**: Mirror existing `test_gateway.py` class structure. Use `gw._format_interrupt_value` and `gw.MESSAGES` since the file already does `import bot.gateway as gw`.
- **IMPORTS**: All inline within tests to mirror existing style — no top-of-file changes.
- **GOTCHA**: `test_renders_today_label` and `test_renders_yesterday_label` use `datetime.now(USER_TIMEZONE)` to compute the ISO date *at test time* — same source the helper uses — so they're robust across midnight rollovers. Don't try to freeze time (overkill).
- **VALIDATE**: `uv run pytest tests/unit/test_gateway.py::TestFormatInterruptValue -v` → all 6 tests pass.

### 10. RUN full unit suite

- **IMPLEMENT**: `uv run pytest tests/unit/ -v`
- **PATTERN**: Pre-commit gate per CLAUDE.md.
- **IMPORTS**: N/A.
- **GOTCHA**: If any test fails, do **not** modify tests to make them pass — diagnose and fix the implementation. The new tests are the spec; existing tests guard against regression.
- **VALIDATE**: All tests green.

### 11. COMMIT

- **IMPLEMENT**: One atomic commit on `ux/hitl-preview-date-and-natural-units` via the `commit` skill:
  - Title: `ux(hitl): show consumed_at date in confirmation preview`
  - Body bullets: graph payload field, gateway date renderer, 4 i18n keys per language, link back to the run1-baseline handoff that surfaced the bug.
- **PATTERN**: Follow the `commit` skill — drafts the commit log + (if non-trivial) PR reading guide and stages everything as one atomic unit. No follow-up `docs:` commit.
- **IMPORTS**: N/A.
- **GOTCHA**: Do not push or open a PR yet — Fix #4 lands on the same branch next, then we open one PR for both fixes.
- **VALIDATE**: `git log -1 --stat` shows changes only in the 5 source files (confirmation_node.py, gateway.py, i18n/__init__.py, en.yaml, he.yaml) plus the 2 test files plus the commit log file.

---

## TESTING STRATEGY

### Unit Tests

**`tests/unit/test_confirmation_node.py::TestFormatBatchPreview`** — three new tests covering the payload shape:
- `consumed_at` defaults to `None` when not passed (back-compat for any caller that doesn't update yet).
- `datetime` input → ISO date string in payload.
- Pre-serialized string input → date-portion string in payload (LangGraph round-trip case).

**`tests/unit/test_gateway.py::TestFormatInterruptValue`** — six new tests covering rendering:
- Missing `consumed_at` → no date line.
- Explicit `None` → no date line.
- Today → today label rendered.
- Yesterday → yesterday label rendered.
- Older date → `D.M` or `M/D` rendered.
- Malformed date → no crash, no date line.

### Integration Tests

Not required for this fix — the change is purely in payload/render shape, no DB or graph-flow change. The existing graph-api `test_log_yesterday_flow.py` (added in PR #26) already exercises the full HITL flow with `consumed_at` set; it will keep passing because nothing about the flow changes, only the payload contents grow.

If you want extra confidence, you *can* add an assertion to `test_log_yesterday_flow.py` that the captured interrupt value contains `consumed_at == "<yesterday-iso>"` — but this is optional, not required.

### Edge Cases

Covered in unit tests:
- `consumed_at` field absent from payload (in-flight checkpoint state from before this fix).
- `consumed_at` is `None` (no date qualifier in user input).
- `consumed_at` is a `datetime` (fresh state).
- `consumed_at` is an ISO string (state round-trip via LangGraph checkpointer).
- `consumed_at` is malformed (defensive — never crash the confirmation flow).
- Today/yesterday/older comparisons use Israel-local time.

NOT covered (deferred — likely a non-issue):
- Future dates (delta < 0) render as a `D.M`/`M/D` date — that's acceptable behavior.
- Year boundary (Jan 1 logging Dec 31) renders as `31.12` / `12/31` without year — acceptable for POC.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

```bash
uv run ruff check src/ bot/ tests/
```

### Level 2: i18n boot check

```bash
uv run python -c "from src.i18n import MESSAGES; print(MESSAGES['confirmation_date_for']); print(MESSAGES['confirmation_date_today'])"
BOT_LANGUAGE=he uv run python -c "from src.i18n import MESSAGES; print(MESSAGES['confirmation_date_for']); print(MESSAGES['confirmation_date_today'])"
```

### Level 3: Targeted unit tests

```bash
uv run pytest tests/unit/test_confirmation_node.py -v
uv run pytest tests/unit/test_gateway.py -v
```

### Level 4: Full unit suite (pre-commit gate)

```bash
uv run pytest tests/unit/ -v
```

### Level 5: Manual smoke (optional but recommended)

Spin up `langgraph dev` + the dev bot in Telegram (or LangSmith Studio with a custom payload):
1. Send: *"אתמול אכלתי 100 גרם חזה עוף"*
2. Expected interrupt text in chat:
   ```
   רגע, בוא נוודא שתפסתי נכון לפני שאני שומר:

   📅 לאתמול

   חזה עוף — 100.0g
   120 קלוריות, 22ג׳ חלבון, 0ג׳ פחמימות, 2.6ג׳ שומן
   ~1 מנת חלבון

   בסך הכל יוצא 120 קלוריות, 22ג׳ חלבון, 0ג׳ פחמימות, 2.6ג׳ שומן.
   ...
   ```
3. Send: *"אכלתי 100 גרם חזה עוף עכשיו"* (today)
4. Expected interrupt text contains `📅 להיום`.
5. Send: *"אכלתי 100 גרם חזה עוף"* (no date qualifier — `consumed_at` likely `None`)
6. Expected interrupt text has **no** `📅` line (preserves the current shape for the default case).

---

## ACCEPTANCE CRITERIA

- [ ] HITL preview payload includes top-level `consumed_at` (ISO date string or `None`).
- [ ] Gateway renders a `📅 ל<label>` / `📅 for <label>` line between the question and the items when `consumed_at` is set.
- [ ] "Today" / "Yesterday" / short-date labels are localized (he/en) via i18n keys.
- [ ] When `consumed_at` is absent or `None`, the date line is omitted (no regression for the common no-date-qualifier case).
- [ ] Malformed `consumed_at` values do not crash the formatter.
- [ ] All four `confirmation_date_*` keys exist in `Messages` TypedDict, `en.yaml`, and `he.yaml`.
- [ ] All unit tests pass; no regressions in existing `TestFormatBatchPreview` cases.
- [ ] No edits outside the 7 expected files (state.py is **not** touched in this plan — `MacroResult` extension is Fix #4's scope).

---

## COMPLETION CHECKLIST

- [ ] All 11 step-by-step tasks completed in order.
- [ ] Each task validation command run and passed.
- [ ] `ruff check` clean.
- [ ] `pytest tests/unit/` green.
- [ ] Manual smoke confirms the date line renders correctly for yesterday + today and is omitted when no date qualifier was given.
- [ ] One atomic commit on `ux/hitl-preview-date-and-natural-units` titled `ux(hitl): show consumed_at date in confirmation preview`.
- [ ] No push, no PR yet — Fix #4 lands on the same branch next.

---

## NOTES

**Why top-level `consumed_at` and not per-item?** The handoff doc suggested per-item `consumed_at`, but `state["log_food"]["consumed_at"]` is a single value per turn — the whole batch shares it. Top-level keeps the payload smaller, the gateway code simpler, and matches the actual semantic shape (one date per HITL session). If we ever add multi-date batches (unlikely — would require a UX where one message logs items across multiple days), per-item is a forward-compat refactor.

**Why ISO date string and not the full datetime?** The user is verifying *which day* they're logging to — the time-of-day is irrelevant to the verification step (and is currently always 12:00:00 for date-qualified logs per the input parser's hierarchy). Smaller payload, simpler comparison logic.

**Why compute "today" on every call instead of caching?** The bot is a long-lived process. Caching "today" at module load would silently serve stale labels after midnight. The `datetime.now(USER_TIMEZONE).date()` call is microseconds-cheap; no need to optimize.

**Out of scope for this plan**:
- Fix #4 (natural-unit rendering) — separate plan, same branch, follow-up commit.
- Year display when crossing years — defer until it actually happens to a user.
- Multi-date batches — defer until UX requires it.
- `consumed_at` on `processing_results` (post-commit summary) — fix here is preview-only; the response_node already injects `consumed_at` into the LLM context for post-commit phrasing per `response_node.py:166`.
