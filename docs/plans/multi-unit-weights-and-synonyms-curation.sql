-- Initial unit_synonyms curation for the 28 non-gram foods in the canonical catalog.
-- Source: prompts/input_parser.md Step 2.7 (the static reference table being dropped in this PR).
--
-- VALIDATION NOTES (read before running):
--   1. This file ASSUMES `unit_weights` and `unit_synonyms` columns already exist
--      and `unit_weights` has been backfilled (Phase 1 of the migration).
--   2. The `||` operator MERGES into existing JSONB without overwriting existing keys.
--      Safe to re-run.
--   3. WHERE clauses use `name_en =` exact match. If your `name_en` values differ,
--      adjust the strings or switch to `ILIKE '%term%'`.
--   4. Hebrew synonyms ("יחידה", "פרוסה", "כף", etc.) are defense-in-depth.
--      The new input parser prompt SHOULD soft-normalize Hebrew → canonical English,
--      but the synonym table is deterministic; this guarantees correctness.
--   5. Skipped foods (egg, apple, banana, etc. with only "יחידה" as alias) — the
--      parser handles "ביצה אחת" → unit="piece" reliably without a synonym entry.
--      Include "יחידה" only where multiple alias forms genuinely help.
--
-- LANGUAGE LEGEND
--   English aliases:  bar/cube/roll/cracker/tin — common alternative words for the same unit.
--   Hebrew aliases:   חתיכה (piece), פרוסה (slice), כף (tbsp), כפית (tsp),
--                     כוס/ספל (cup), בקבוק (bottle), פחית/קופסה (can), מדה/מדידה (scoop).
--                     "יחידה" = "unit/piece", a generic Hebrew countable.

BEGIN;

-- ============================================================================
-- piece-bucket — alternative words users actually say
-- ============================================================================

-- Protein bar — users say "bar" more than "piece"
UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"bar": "piece", "יחידה": "piece"}'::jsonb
WHERE name_en = 'protein bar';

-- Protein pudding — comes in a container/cup, users may say "cup" or "container"
UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"cup": "piece", "container": "piece", "מיכל": "piece", "יחידה": "piece"}'::jsonb
WHERE name_en = 'protein pudding';

-- Bread roll — English speakers say "roll", Hebrew "יחידה"
UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"roll": "piece", "יחידה": "piece"}'::jsonb
WHERE name_en = 'bread roll';

-- Rice cake — "cracker" / "cake" / "פריכית"
UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"cracker": "piece", "cake": "piece", "יחידה": "piece"}'::jsonb
WHERE name_en = 'rice cake';

-- Para chocolate cubes — comes as cubes; "cube" / "קובייה"
UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"cube": "piece", "קובייה": "piece", "קוביה": "piece", "יחידה": "piece"}'::jsonb
WHERE name_en = 'Para chocolate cubes';

-- Kinder Bueno — sold as bar/stick
UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"bar": "piece", "stick": "piece", "יחידה": "piece"}'::jsonb
WHERE name_en = 'Kinder Bueno';

-- Dates — Hebrew "תמר" (singular) is what users will say for one date
UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"תמר": "piece", "יחידה": "piece"}'::jsonb
WHERE name_en = 'dates';

-- Egg, white pita, laffa, apple, banana — "piece" is so universal that
-- the parser handles them without synonyms. Skip unless evidence shows otherwise.

-- ============================================================================
-- slice-bucket — bread + cheese; users say "piece" or "חתיכה" all the time
-- ============================================================================

-- White bread
UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"piece": "slice", "חתיכה": "slice", "פרוסה": "slice"}'::jsonb
WHERE name_en = 'white bread';

-- Yellow cheese 9%
UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"piece": "slice", "חתיכה": "slice", "פרוסה": "slice"}'::jsonb
WHERE name_en = 'yellow cheese 9%';

-- Yellow cheese regular
UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"piece": "slice", "חתיכה": "slice", "פרוסה": "slice"}'::jsonb
WHERE name_en = 'yellow cheese regular';

-- ============================================================================
-- scoop-bucket — protein supplements
-- ============================================================================

-- Whey protein — Hebrew "מדה"/"מדידה" = measure/scoop
UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"מדה": "scoop", "מדידה": "scoop", "מנה": "scoop"}'::jsonb
WHERE name_en = 'whey protein';

-- ============================================================================
-- bottle-bucket
-- ============================================================================

-- Yotvata Pro
UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"בקבוק": "bottle"}'::jsonb
WHERE name_en = 'Yotvata Pro';

-- Beer — usually bottle, sometimes can. Cans have a different mL than bottles,
-- so do NOT add "פחית"→"bottle" — it'd be the wrong weight. If users log canned
-- beer often, add a separate `unit_weights["can"]` entry instead.
UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"בקבוק": "bottle"}'::jsonb
WHERE name_en = 'beer';

-- ============================================================================
-- cup-bucket
-- ============================================================================

-- Protein yogurt — sold in containers; users may say "yogurt" / "container" / "כוס"
UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"container": "cup", "מיכל": "cup", "כוס": "cup"}'::jsonb
WHERE name_en = 'protein yogurt';

-- Black coffee
UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"mug": "cup", "כוס": "cup", "ספל": "cup"}'::jsonb
WHERE name_en = 'black coffee';

-- Tea
UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"mug": "cup", "כוס": "cup", "ספל": "cup"}'::jsonb
WHERE name_en = 'tea';

-- ============================================================================
-- tbsp-bucket — Hebrew "כף" universally maps to tbsp
-- ============================================================================

UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"כף": "tbsp", "spoon": "tbsp"}'::jsonb
WHERE name_en = 'mayonnaise';

UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"כף": "tbsp", "spoon": "tbsp"}'::jsonb
WHERE name_en = 'tahini raw';

UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"כף": "tbsp", "spoon": "tbsp"}'::jsonb
WHERE name_en = 'olive oil';

-- ============================================================================
-- tsp-bucket — Hebrew "כפית" universally maps to tsp
-- ============================================================================

UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"כפית": "tsp"}'::jsonb
WHERE name_en = 'sugar';

-- Peanut butter — note: tsp is the curated unit, but users often say tbsp.
-- If your curation is wrong (peanut butter at 1 tsp seems small), update unit_weights
-- separately, not via synonyms.
UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"כפית": "tsp"}'::jsonb
WHERE name_en = 'peanut butter';

-- ============================================================================
-- can-bucket — tuna
-- ============================================================================

UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"tin": "can", "קופסה": "can", "פחית": "can", "קופסת": "can"}'::jsonb
WHERE name_en = 'tuna in water';

UPDATE food_items
SET unit_synonyms = unit_synonyms || '{"tin": "can", "קופסה": "can", "פחית": "can", "קופסת": "can"}'::jsonb
WHERE name_en = 'tuna in oil';

-- ============================================================================
-- VERIFICATION (read-only, safe to run repeatedly)
-- ============================================================================

-- Check what got curated. Should return ~22 rows (the foods with synonyms above;
-- egg/apple/banana/etc. intentionally skipped).
SELECT
    name_en,
    name_he,
    unit_weights,
    unit_synonyms
FROM food_items
WHERE unit_synonyms != '{}'::jsonb
ORDER BY name_en;

-- Sanity check: every synonym's canonical key must exist in unit_weights.
-- This query returns rows where a synonym points to a non-existent weight key.
-- Expected: empty result.
SELECT
    name_en,
    unit_weights,
    unit_synonyms,
    s.key AS synonym_alias,
    s.value AS canonical_target
FROM food_items, jsonb_each_text(unit_synonyms) s
WHERE NOT (unit_weights ? s.value)
ORDER BY name_en;

COMMIT;
