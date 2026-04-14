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

**Step 3 — Protein**
- 2.0 g/kg (use target weight, not current, if BF > 25%)
- 2.3 g/kg if BF < 13%, spread across 3 meals
- Only complete proteins count; min 20g per serving
- Protein calories = grams × 4

**Step 4 — Fat (verify, don't add)**
- Assume mid-range protein sources (not leanest, not fattiest). Rough estimate:
  - Lean options average ~3g fat per 20g protein
  - Mid-range average ~6–8g fat per 20g protein
  - Fatty options ~12g fat per 20g protein
- Pick mid-range → multiply by protein servings → fat grams
- Sanity check: fat should land in ~0.8–1.2 g/kg. If outside, nudge the estimation toward leaner or fattier sources.
- Fat calories = grams × 9

**Step 5 — Discretionary**
- Carve out 100 cal/day for sauces, milk in coffee, small treats

**Step 6 — Weekly carb budget**
- `daily_carb_cal = daily_intake − protein_cal − fat_cal − discretionary_cal`
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
