# Hebrew translations + conversational HITL + passphrase non-ASCII fix

**Date**: 2026-04-16
**Branch**: i18n-message-extraction
**Commits**:
- `2acc258` feat: translate i18n to hebrew and rewrite hitl confirmation as prose
- `<next>` fix: handle non-ascii first message in passphrase check

## Changes

### Hebrew translations filled in
- All 21 keys in `src/i18n/he.yaml` now have real Hebrew values (zero `TODO_HE` remaining).
- Dolev provided 17 translations in his voice (casual, slightly cheeky); Claude filled the remaining 4 in matching tone.
- Specific choices flagged / discussed:
  - `confirmation_estimated_tag: " (משוערך)"` (switched from `(בערך)` per user request)
  - `confirmation_macro_line: "{cals} קלוריות, {protein}ג׳ חלבון, {carbs}ג׳ פחמימות, {fat}ג׳ שומן"` — full Hebrew labels (קלוריות, חלבון, פחמימות, שומן) with `ג׳` (grams) geresh
  - `confirmation_total_line` — starts with `בסך הכל יוצא` instead of the abbreviated `סה״כ`
  - `auth_registration_error` — user's translation reads more like "wrong passphrase" tone; flagged as semantic mismatch against the actual code path (tech failure, not user error). Left as-written.

### Conversational HITL confirmation rewrite
Both EN and HE softened from receipt-like to prose-like. Changes span:
- `confirmation_question` — new friendly opener (`"Let me double-check these before I save them:"` / `"רגע, בוא נוודא שתפסתי נכון לפני שאני שומר:"`)
- `confirmation_macro_line` — prose (`"{cals} kcal, {protein}g protein, ..."`) instead of table row with pipes. 2-space indent removed from YAML value.
- `confirmation_total_line` — narrative (`"Altogether that's ..."` / `"בסך הכל יוצא ..."`)
- `confirmation_reply_hint` — conversational call-to-action
- `_format_interrupt_value` in `bot/gateway.py` — drop the `•` bullet, drop the indent under the food name, add `\n\n` between items so each breathes

Renderer now uses a `sections` list joined by `\n\n` for cleaner flow.

### Duplicate (estimated) tag bug fixed
Pre-existing latent bug uncovered during live HE rendering test:
- `_format_batch_preview` (graph) appended the estimated tag to `description`
- `_format_interrupt_value` (bot) also appended the estimated tag after `description`
- Result: `(estimated) (estimated)` (or `(משוערך) (משוערך)`)
- Fix: removed the bot's append. Graph owns the tag; bot just renders `description` as-is.

### Language-brittle tests fixed
- `test_estimated_item_tag` now checks `MESSAGES["confirmation_estimated_tag"]` substring + asserts on `source` field (both language-agnostic).
- `test_onboarding_validates_height` now asserts `mock_message.answer.assert_called_with(gw.MESSAGES["onboarding_invalid_height"])` instead of substring-checking for the English word `"number"`.
- Both now pass under `BOT_LANGUAGE=en` or `he`.

### Passphrase non-ASCII crash (separate commit)
Pre-existing bug: `hmac.compare_digest(message.text.strip(), BOT_PASSPHRASE)` raises `TypeError: comparing strings with non-ASCII characters is not supported` when the user's first message contains non-ASCII chars (Hebrew, emoji, accented text). Python's `hmac.compare_digest` refuses non-ASCII strings for timing-attack safety.

Fix: encode both operands to UTF-8 bytes before comparing. `compare_digest` works natively on bytes, constant-time comparison guarantee preserved.

This would have silently blocked every Hebrew-speaking user who typed `"היי"` before entering the passphrase.

## Validation

- `uv run pytest tests/unit/ -q` → **121 passed**
- Live rendered HE preview matches expected prose format, no duplicate tags
- EN preview also updated to match the new conversational shape

## Next Steps

- **Restart bot locally** → re-test flow in Telegram with `BOT_LANGUAGE=he` in `.env`
- **Audit remaining Hebrew strings** for tone if any feel off to Dolev after seeing them rendered
- **CI run** on push will exercise the new tests
- **Merge** PR #22 when Hebrew smoke test passes

## Out of scope / follow-ups (still)

- Food names in `food_items` DB are still English (`chicken`, `pizza`) — localizing the food catalog is a separate pass.
- Amount + unit format `f"{food_name} — {amount_g}g"` in `_format_batch_preview` uses English `g`. Could be `גרם` with a new key + code change, but not critical for the POC.
