# ux(hitl): show consumed_at date in confirmation preview

**Branch**: `ux/hitl-preview-date-and-natural-units`
**Plan**: `docs/plans/hitl-preview-show-consumed-at.md`
**Source**: UX Fix #5 from `brain/TASKS.md` (Important — Real User Quality), surfaced via `tests/ux-loop/log-yesterday-and-today-then-query/runs/run1-baseline/` handoff record.

## What changed

When the user logs a meal with a date qualifier ("אתמול אכלתי..." / "yesterday I ate..."), the HITL preview now shows the routing date so the user can verify it before confirming. Previously the preview rendered food / amount / macros / servings / category but no date — even though the bot had correctly extracted "yesterday" and the DB write was landing on the right row. Asking the user to confirm a date they cannot see is the wrong UX shape for a confirmation step.

```
Before:                              After:
רגע, בוא נוודא...                   רגע, בוא נוודא...

חזה עוף — 100.0g                    📅 לאתמול
120 קלוריות, 22ג׳ חלבון...
                                    חזה עוף — 100.0g
                                    120 קלוריות, 22ג׳ חלבון...
```

Date line is rendered only when `consumed_at` is set (i.e. user used a date qualifier or the input parser inferred one). The default no-date-qualifier flow keeps the previous shape — no extra visual noise on every "what did I just eat" log.

## File-by-file

| File | Change |
|---|---|
| `src/i18n/__init__.py` | Added 4 keys to `Messages` TypedDict: `confirmation_date_for`, `confirmation_date_today`, `confirmation_date_yesterday`, `confirmation_date_other`. Parity check enforces both YAMLs supply them. |
| `src/i18n/en.yaml` | Added 4 EN values. Date format: `M/D` (no year). |
| `src/i18n/he.yaml` | Added 4 HE values. Date format: `D.M` (no year). Uses `📅 ל{date_label}` (no space — Hebrew lamed prefix attaches directly). |
| `src/agents/nodes/confirmation_node.py` | `_format_batch_preview(items, consumed_at=None)` — accepts optional date, emits top-level `consumed_at` ISO date string in payload. Defensive handling for both `datetime` and `str` (LangGraph state round-trip). Both call sites in `confirmation_node` (initial preview + post-edit re-render) pass `state["log_food"]["consumed_at"]`. |
| `bot/gateway.py` | New `_format_date_label(iso_date)` helper. Compares to today in Israel local (`USER_TIMEZONE`), returns `today` / `yesterday` / `D.M` (he) or `M/D` (en) wrapped by `confirmation_date_for`. Returns `None` on parse failure so the formatter skips the line rather than crashes. `_format_interrupt_value` renders the date line **between** the question and the items — framing what follows. |
| `tests/unit/test_confirmation_node.py` | 3 new `TestFormatBatchPreview` cases: default `None`, `datetime` → ISO date, pre-serialized string → date portion. |
| `tests/unit/test_gateway.py` | New `TestFormatInterruptValue` class: 6 cases covering missing / `None` / today / yesterday / older date / malformed. |

## Verification

- **Lint**: `ruff check src/ bot/ tests/` — clean.
- **Unit**: `uv run pytest tests/unit/` — **168 passed** (was 159 before this change; +9 new tests, no existing tests modified).
- **i18n boot**: `MESSAGES` loads cleanly under `BOT_LANGUAGE=en` and `BOT_LANGUAGE=he`. Parity check enforces drift will fail loudly at import time.
- **Helper smoke**: `_format_date_label` on `2026-05-07` (yesterday) / `2026-05-08` (today) / `2026-01-15` (other) / `not-a-date` (malformed) returns the expected labels and `None` respectively.

## Why these decisions

- **Top-level `consumed_at` (not per-item)**: `state["log_food"]["consumed_at"]` is one value per turn; the whole batch shares it. Per-item would carry redundant data and complicate the gateway. The handoff doc suggested per-item; we deliberately diverged.
- **ISO date string (not full datetime)**: the user is verifying *which day*, not what time. The time-of-day for date-qualified logs is always 12:00:00 today (input parser convention), so it adds no signal. Smaller payload, simpler comparison.
- **Always render when `consumed_at` is set, including today**: removes the "did the bot understand 'now' meant today?" ambiguity. Costs one extra line in the case where the user explicitly said a date — which is exactly when they want the verification.
- **Compute "today" per-call (not at module load)**: the bot is long-lived; a cached "today" would silently serve stale labels after midnight.
- **`str(consumed_at)[:10]` for the round-trip case**: ISO datetime strings start with `YYYY-MM-DD`; substring is faster than parse-then-reformat and side-steps a `fromisoformat` failure on edge formats.

## What's next

Same branch → Fix #4 (HITL drops natural units like "2 שתי פרוסות גבינה" — preview shows `50g`, not `2 פרוסות`). Plan + commit will land here as a follow-up before opening the PR for both fixes together.

After that → re-run the UX loop `log-yesterday-and-today-then-query` as `run2-hitl-fixes` to verify the bug is gone end-to-end and capture the new artifacts.
