---
name: build-cut-plan
description: Build a personalized CUT (fat-loss) nutrition plan through a conversational intake, compute daily macros and weekly carb distribution, then emit the full plan as a markdown file with interchangeable serving options (like the Dor Eckstein-style menus). Use whenever the user asks to "build a cut plan", "create a diet plan", "design a fat-loss menu", "תפריט קאט", "תפריט הרזיה", or wants a structured nutrition plan based on the FitPal method. Output language is Hebrew (RTL-rendered) or English — ask the user which. Trigger even when the user doesn't explicitly say "cut" but describes fat-loss goals with weight/BF inputs.
---

# Build Cut Plan

Guide the user through a 5-part conversation to produce a complete cut-phase nutrition plan. The plan follows the method in `docs/nutrition-method.md` (project root) and mirrors the Dor Eckstein "ייעוץ תזונה" PDF structure — options-based menus where every line is one full serving of equivalent macros.

**Output language**: ask the user early. Hebrew plans render RTL automatically in Obsidian reading view (no `<div>` wrapper — Obsidian doesn't parse markdown inside raw HTML). English plans use standard LTR markdown.

## Why this shape

The plan is not a fixed daily menu. It is (1) **targets** (calories, protein, carbs) plus (2) **interchangeable serving options** the trainee combines freely. This matches how people actually eat and makes the plan adaptable. Your job is to compute the targets correctly and translate them into serving units.

## Conversation flow

Ask questions in small batches (3–4 at a time), not all at once. Confirm each computed number before moving on.

### Part 1 — Intake

Collect in this order:

1. **Language preference** — Hebrew or English output
2. **Body**: sex, age, weight (kg), height (cm), body fat % (caliper if they have one; else best estimate)
3. **Training**: sessions per week (strength), preferred time of day, injuries
4. **Schedule**: wake time, sleep time, typical work hours
5. **Eating baseline**: current meals/day, first meal time, water/coffee/alcohol intake
6. **Rest-day carb floor** — ask directly: *"On a rest day, what's the minimum carb amount you can handle without feeling starved? (examples: 30g, 50g, 80g)"*. This is a first-plan number, not zero.
7. **Preferences**: foods disliked, allergies, dietary restrictions, favorite protein sources

### Part 2 — Classify and compute targets

Confirm the **phase** first:
- BF > 25% → overweight protocol (see `references/method-rules.md` §overweight)
- BF 13–25% → standard cut
- BF < 13% → low-BF cut (protein 2.3 g/kg, 3 meals, 12h fast max)

Then compute, showing each step in chat:

**Step 1 — TDEE** (Mifflin-St Jeor × activity)
- Male BMR = `10×kg + 6.25×cm − 5×age + 5`
- Female BMR = `10×kg + 6.25×cm − 5×age − 161`
- Activity multiplier based on training frequency + job style:
  - sedentary desk job, 0–1 sessions: 1.2
  - light (2 sessions, mostly desk): 1.375
  - moderate (3 sessions, some walking): 1.55
  - heavy (4+ sessions or physical job): 1.725

**Step 2 — Deficit target**
- 25% deficit from TDEE
- Hard cap: `70 × kg_body_fat` (never exceed — body will break down muscle)
- Take the smaller of the two
- Daily intake target = TDEE − deficit

**Step 3 — Protein target (grams + servings)**
- 2.0 g/kg (use target weight, not current, if BF > 25%)
- 2.3 g/kg if BF < 13%, spread across 3 meals
- Only complete proteins count; min 20g per serving
- Divide by 20 → **number of protein servings per day**

**Step 4 — Protein skeleton calories (food-based, not macro math)**

This is the biggest mental shift: **do not** calculate protein calories as `grams × 4` and then fat as a separate add-on. The trainee eats *foods*, and each food brings its protein and its native fat together. Estimate the calories the trainee will actually consume from their protein servings.

How to estimate:
- Each protein serving in `references/serving-options.md` lists `kcal_per_serving` (calories for the food amount that delivers 20g protein)
- Values span roughly 130 kcal (very lean, e.g. white fish) → 250 kcal (fatty, e.g. ribeye, salmon, fatty cheese)
- **Default anchor: 170 kcal/serving** — realistic mix for someone who eats mostly lean-to-mid sources with occasional fattier meals (chicken breast, lean beef, cottage 3%, eggs, salmon here and there)
- `protein_skeleton_cal = protein_servings × 170`

Example check — 200g chicken breast ≈ 330 kcal, 200g ribeye ≈ 570 kcal. The 170 kcal/serving anchor assumes a mostly-lean mix with some variety. Adjust downward (145–155) if the trainee is very strict about lean-only; upward (185–200) if they truly lean fatty.

The fat does **not** need separate verification — it's already inside the skeleton calorie number. If the trainee eats leaner than the estimate, they'll have more calories left for carbs (good). If fattier, carbs tighten.

**Step 5 — Two separate 100-kcal buckets (pre-allocated off the top)**

These are two different things — keep them separate in the plan, both in the calculation and in the output file.

1. **Background allowance — 100 kcal/day**
   - Covers incidental calories that happen anyway: cooking oil spray, milk in coffee, sauce drizzle, dressings
   - NOT the trainee's choice — it's a realistic buffer so the plan math matches real life
   - Used daily, not aggregatable

2. **Free calories — 100 kcal/day**
   - The trainee picks what to spend it on: wine, chocolate, fruit, tahini, mayo, etc.
   - **Aggregatable across days** — skip Monday+Tuesday → 300 kcal available Wednesday for a glass of wine + chocolate
   - The output plan MUST include an examples list (≈100 kcal equivalents: 1 apple / 1 banana / 3 dates / 60ml whiskey / 125ml wine / 6 chocolate squares / 1 tbsp tahini / 1.5 tbsp olive oil / 2 tbsp mayo / 3 tsp peanut butter / etc.)

**Step 6 — Weekly carb budget**
- `daily_carb_cal = daily_intake − protein_skeleton_cal − 100 (background) − 100 (free)`
- `weekly_carb_g = 7 × daily_carb_cal / 4`

**Step 7 — Distribute carbs across the week**
- Rest days get the trainee's stated floor (from intake Q6)
- Training days get the remainder, split across those days
- Within a training day: non-post-workout carbs capped at 50g; rest loaded post-workout
- Example for 3 training days, 4 rest days, floor 50g, weekly budget 700g:
  - Rest days: 4 × 50 = 200g
  - Training days: (700 − 200) / 3 ≈ 167g each → 50g regular + 117g post-workout

**Step 8 — Convert grams to servings**
- 1 carb serving = 50g carbs
- 1 protein serving = 20g complete protein
- Express daily targets as integer serving counts (e.g. "7 protein servings, 2 carb servings")

Show the user a summary table of all numbers before generating the file. Let them adjust.

### Part 3 — Build the menu

Use serving tables from `references/serving-options.md`. Each menu slot lists multiple equivalent options — the trainee picks any combination to hit the serving count.

Meal structure for cut:

| Meal | When | Contents |
|---|---|---|
| Lunch | 3+ hours after waking (break the fast) | 2 protein servings + greens + 0 or 1 carb serving |
| Mid-day snack (optional) | Between lunch and dinner | 1 protein serving + optional 1 light carb serving |
| Dinner | Evening | 2 protein servings + vegetables + 1 carb serving |
| Post-workout loading meal | 1h after strength session (training days only) | 2 protein servings + 3+ carb servings, lean, no fiber |

Adjust serving counts based on the trainee's actual daily protein + carb targets.

### Part 4 — Emit the plan file

Write the plan to `docs/plans/cut-plan-{username}-{YYYY-MM-DD}.md` (ask for username or use `me`). Use the template at `assets/plan-template-{lang}.md` and fill in computed values.

**Hebrew output**: no `<div dir="rtl">` wrapper — plain Hebrew renders RTL in Obsidian reading view. Use tables, bullets, headings normally.

**English output**: standard markdown, LTR.

The file must include:
- Trainee snapshot (body data, goal, training days)
- Daily targets table (calories, protein, carbs, servings)
- Rest-day vs training-day carb targets
- Meal sections with interchangeable options
- Post-workout loading options (home + outside)
- Rules sheet (timing, fasting, hydration, discretionary cals, alcohol, etc.)
- Weights dictionary (common reference weights for weighing-by-eye)

### Part 5 — Confirm and hand off

After writing the file, tell the user where it is, summarize the key numbers, and offer to:
- Tweak any targets (they may push back on the deficit, protein sources, etc.)
- Build the corresponding training plan (out of scope for this skill — note it as a follow-up)

## References

- **Method rules** — `references/method-rules.md`: condensed version of `docs/nutrition-method.md` focused on cut-phase rules, formulas, and edge cases. Read this when you need to justify a number or handle an edge case.
- **Serving tables** — `references/serving-options.md`: pre-built lists of 1-protein-serving and 1-carb-serving options in both Hebrew and English. Copy from here into the plan file.
- **Templates** — `assets/plan-template-he.md` and `assets/plan-template-en.md`: skeletons to fill in. Structure mirrors the Dor Eckstein PDF.

## Important behaviors

- **Show your math.** When computing TDEE, deficit, protein, carb budget — print the formula and the numbers. The user learns the method from watching the calculation.
- **Confirm before writing the file.** Don't assume. Present the final targets table and ask "look good?" before generating.
- **Don't invent food data.** Use only the options from `references/serving-options.md`. If the user asks for a food not listed, compute the serving equivalence explicitly from macros per 100g.
- **First plan is not optimal — it's safe and livable.** Don't push zero-carb rest days or extreme deficits on a new plan. Note in the output that adjustments come after 2–3 weeks of data.
