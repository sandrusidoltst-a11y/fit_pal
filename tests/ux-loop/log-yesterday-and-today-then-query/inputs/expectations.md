# Expectations

## Dimensions

### log-correctness
**What:** when the user logs a meal with a date qualifier (today, yesterday, etc.), the bot's HITL preview shows the correct date and the resulting DB row lands on that date.
**How to evaluate:** pass/fail per logged turn.
- pass: HITL preview shows the date the user specified (or today if no qualifier was given), and the DB query (Step 3) confirms a row exists with the matching `timestamp` date.
- fail: preview shows wrong date, DB row lands on wrong date, or no row appears.
**Output:** `pass` / `fail` per logged turn + the actual date observed in the HITL preview and in the DB row.

### historical-query-retrieval
**What:** when the user asks "what did I eat <time qualifier>", the bot returns actual logged data for that range — not "I only see today" or hallucinated entries.
**How to evaluate:** pass/fail per query turn.
- pass: the reply enumerates real logged items from the queried range (verifiable against DB state from Step 3).
- fail: the bot says it can't retrieve the data, says "I only see today", returns nothing, or invents entries not in the DB.
**Output:** `pass` / `fail` per query turn + one short quote from the bot's reply that justified the verdict.

### time-and-intake-awareness
**What:** on a today-query reply, the bot demonstrates situational awareness — it reasons about the current time-of-day, what's been logged today, and how that compares to the plan. The check is: did the bot react to the situation, or did it just dump the log? Example failure: it's 3pm, the user has logged only 100g chicken today, and the bot replies "you ate 100g chicken" without flagging that this is light for the time of day vs. the plan.
**How to evaluate:** checklist — all four items must hold for pass.
- references the current time-of-day (explicitly, or via meal-pacing reasoning that implies it)
- references what was actually consumed today (matches DB state — no hallucinated items)
- contextualizes against the plan — what's still missing, whether the user is on/off pace, or what makes sense to eat next
- avoids the robotic log-dump (does more than list items without comment)
**Output:** `pass` / `fail` + which checklist items failed (1 short bullet per failed item).

### tone
**What:** the bot sounds like a human coach having a conversation — supportive but grounded, not sycophantic or hype-flooded. The voice should feel like a coach on WhatsApp, not a chatbot and not a motivational poster.
**How to evaluate:** 0-3 rubric.
- 3 = conversational, lightly supportive, sounds like a human coach. Encouragement is grounded in the user's actual state, not generic.
- 2 = mostly natural but occasionally flat or generic (`"מעולה!"`, `"כל הכבוד!"` without specifics).
- 1 = noticeably robotic/transactional, or overly enthusiastic with empty positivity (cascading exclamation marks, "amazing!" / "wonderful!" / "you're doing great!" without grounding).
- 0 = breaks tone entirely — apologetic, contradictory, or hype-flood that ignores the actual user state.
**Output:** integer 0-3 + one-sentence justification quoting the line that drove the verdict.

### language-consistency
**What:** the bot replies in the user's language with no mid-reply switches, including nutrition vocabulary (`מנות`/`servings`, `חלבון`/`protein`, `ג׳`/`g`).
**How to evaluate:** pass/fail.
- pass: every word in the reply is in the user's language.
- fail: any English word inside a Hebrew reply (or vice versa). Numbers and units like `100g` count as a fail in Hebrew context — should be `100 ג׳`.
**Output:** `pass` / `fail` + the offending word(s) on fail.

## Regression thresholds

Baseline experiment: `ee5723d2-dc46-4011-8a98-56f6b5bdc5a7` (`input-parser-hebrew-gpt-5.4-mini-ca909381`).
Mode: read existing — Step 0 fetches scores without re-running.

Coverage caveat: this eval covers input-parser quality only (`prompts/input_parser.md`). Sessions that edit `prompts/response_generator.md` or other prompts are not regression-checked by this eval — surface that gap in findings if it applies.

| Metric | Baseline | Threshold |
|---|---|---|
| `correct_action` | 97.14% | `max -2pp` |
| `correct_dates` | 88.57% | `max -3pp` |
| `correct_item_count` | 100% | `no drop` |
| `correct_serving` | 85.71% | `max -3pp` |
| `food_name_quality` | 100% | `no drop` |
| `no_consumed_at_on_query` | 100% | `no drop` |
| `no_query_dates_on_log_food` | 100% | `no drop` |

## Behavioral rules

- when: turn expected `interrupt` but bot returned `final`
  do: record finding (dimension: log-correctness, severity: high), abort scenario, continue to next

- when: turn expected `final` but bot returned `interrupt`
  do: record finding (severity: med), send adaptive resume to clear the interrupt, continue

- when: dimension `log-correctness` scored fail on a turn
  do: record finding (severity: high), continue — don't abort, the rest of the scenario tests how the bot handles the resulting state

- when: dimension `historical-query-retrieval` scored fail on a turn
  do: record finding (severity: high), continue

- when: dimension `time-and-intake-awareness` scored fail
  do: record finding (severity: high), continue — this is the core dimension this scenario was designed to test

- when: dimension `tone` scored below 2
  do: record finding (severity: med), continue

- when: dimension `language-consistency` scored fail
  do: record finding (severity: high), continue

- when: any FAILED processing_result in trace
  do: record finding (dimension: pipeline, severity: high), continue

- when: bot returns no response within 60s
  do: abort scenario, record finding (severity: high, bucket: pipeline)
