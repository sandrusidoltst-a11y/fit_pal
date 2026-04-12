# Response Generator Prompt — Coaching Method & Nutrition Principles

**Date**: 2026-04-12
**Tag**: feat

## Changes

### What
Rewrote `prompts/response_generator.md` from a generic fitness chatbot prompt into a structured coaching system prompt. The prompt now contains:

- **Identity & Tone**: Direct, honest, brief — not overly pleasing
- **About This Prompt**: Meta-section explaining the prompt contains both principles and specific action instructions
- **Time Awareness**: Instructions for contextual feedback based on time of day (requires current time injection — not yet wired)
- **Coaching Method Overview**: Core philosophy (protein non-negotiable, carbs fuel workouts, avoid added fat, meal timing, consistency > perfection, plan is authority)
- **Macro-specific rules**: Protein (complete sources only, 20g minimum per serving), Carbs (starch-based only, post-workout priority), Fat (not tracked, flag added fats)
- **Meal Timing**: Fasting window (~10am), post-workout window (1-2hr), stop eating by 10pm
- **General knowledge**: Hydration, flexibility/discretionary calories, alcohol, sleep/stress, motivation

### Context
This is part of the nutrition plan feature — adding per-user meal plans and coaching intelligence to FitPal for the mid-May POC. The prompt was designed section-by-section with Dolev based on principles from a nutrition course he took.

### Also in this session (committed separately)
- PRD updated with nutrition plan history feature (future item)
- `.gitignore` updated to exclude `docs/nutrition-method.md` (private course notes)
- `docs/nutrition-method.md` created by sub-agent from 39 course PDFs (gitignored)

## Next Steps
- Create implementation plan for the full nutrition plan feature
- Wire current time injection into `response_node.py`
- Add `nutrition_plan` text column to `UserProfile` model
- Wire plan text through `ContextSchema` → `response_node` system prompt
- Update input parser prompt to route plan-vs-actual questions to `QUERY_DAILY_STATS`
- Create `set_plan.py` script for coach to upload plans per user
- Test the prompt with real food logging scenarios
