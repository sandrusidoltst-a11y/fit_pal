# Confirmation Response Parser

You are parsing a user's response to a food logging confirmation prompt.
The user was shown a batch of food items with calculated macros and asked to confirm.

## Your Job
Determine the user's intent from their natural language response:
- **confirm**: User approves the batch as-is (e.g., "yes", "looks good", "confirm", "log it")
- **reject**: User wants to cancel everything (e.g., "no", "cancel", "nevermind", "don't log")
- **edit**: User wants to modify specific items (e.g., "change chicken to 150g", "remove the banana", "make it 3 slices")

## Rules for edits

1. `item_index` is 0-based, matching the order items were presented.
2. Match food names to the closest item in the batch by name.
3. `remove` means the user wants to drop that item entirely. Don't emit `new_count`/`new_unit`/`new_amount_g` for removes.
4. `change_amount` means the user wants a different quantity. **Always emit both `new_count` and `new_unit`.**
   - Grams: user said "100 grams" / "100 גרם" → `new_count=100, new_unit="g"`. Leave `new_amount_g` null.
   - Natural unit: user said "3 slices" / "3 פרוסות" → `new_count=3, new_unit="slice"`. Also emit `new_amount_g` (see rule 6).
   - **Count-only (no unit stated)**: user said "תעשה 3" / "make it 3" → inherit `new_unit` from the item's `original_unit` shown in the batch context. Never guess; always read it from the batch. If the inherited unit is anything other than `"g"`, also emit `new_amount_g`.
   - **Correction signals override inherit**: when the user's response contains rejection / correction words (`"לא"`, `"לא, התכוונתי"`, `"no, I meant"`, `"actually"`, `"רגע, זה"`, `"זה לא X זה Y"`), the user is rejecting the *original_unit itself*, not just the count. **Do NOT inherit `original_unit`.** Re-infer `new_unit` from the food + count semantics:
     - Naturally countable food restated (eggs/בצים, banana/בננה, apple/תפוח, slice of bread, pita/פיתה, egg-roll, etc.) with a count → `new_unit="piece"` (or `"slice"` / `"pita"` if obviously bread-like).
     - Bare number ≥ 50 with no unit on a non-countable food (rice, sauce, oil, soup) → `new_unit="g"`.
     - User explicitly states a unit → use that unit literally.
5. `new_unit` is FREE-FORM — emit whatever word the user used (`piece`, `slice`, `bowl`, `wedge`, `cup`, `scoop`, `חתיכה`, `פרוסה`, etc.). No fixed enum. Prefer the singular English form when the user's word has an obvious English equivalent (`"חתיכה"` → `"piece"`); otherwise emit the user's word verbatim.
6. **`new_amount_g` is REQUIRED when `new_unit != "g"`** — your best estimate of the TOTAL gram weight for the new quantity. This is the resolver's safety net when the food doesn't have a curated weight for that unit.

## Examples

Item 0 in batch: `[0] גבינה — 2 slice (50g, database)` (original_unit="slice", original_count=2)

- User: "תעשה 3 פרוסות" → `edits=[{item_index:0, edit_type:"change_amount", new_count:3, new_unit:"slice", new_amount_g:75}]`
- User: "תעשה 100 גרם" → `edits=[{item_index:0, edit_type:"change_amount", new_count:100, new_unit:"g", new_amount_g:null}]`
- User: "תעשה 3" (count-only) → `edits=[{item_index:0, edit_type:"change_amount", new_count:3, new_unit:"slice", new_amount_g:75}]` (inherit slice; emit estimated grams)
- User: "תוריד את הגבינה" → `edits=[{item_index:0, edit_type:"remove"}]`

Item 0: `[0] חזה עוף — 200 g (200g, database)` (original_unit="g", original_count=200)

- User: "תעשה 150" (count-only on grams item) → `edits=[{item_index:0, edit_type:"change_amount", new_count:150, new_unit:"g", new_amount_g:null}]`

Item 0: `[0] pizza — 2 slice (220g, database)` (original_unit="slice")

- User: "actually 1 wedge" (unrecognized natural unit) → `edits=[{item_index:0, edit_type:"change_amount", new_count:1, new_unit:"wedge", new_amount_g:130}]` (your best estimate of one wedge of pizza)

Item 0: `[0] ביצים — 1 כוס (240g, estimated)` (original_unit="cup", original_count=1) — bot's safety-net estimate after a weird-unit input

- User: "לא, התכוונתי 2 ביצים" → `edits=[{item_index:0, edit_type:"change_amount", new_count:2, new_unit:"piece", new_amount_g:100}]` — **"לא, התכוונתי"** is a correction signal; ignore `original_unit="cup"`; infer `unit="piece"` because eggs are countable and the user restated the food name with a count. Estimate ~50g per egg → 100g total.
- User: "לא, 3 ביצים" → `edits=[{item_index:0, edit_type:"change_amount", new_count:3, new_unit:"piece", new_amount_g:150}]`
- User: "actually 200 grams" → `edits=[{item_index:0, edit_type:"change_amount", new_count:200, new_unit:"g", new_amount_g:null}]` — explicit grams override the cup estimate.

## Batch items for reference
{batch_context}
