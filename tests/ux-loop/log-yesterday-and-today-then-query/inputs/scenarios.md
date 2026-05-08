## Scenario: log-yesterday-and-today-then-query
**Goal:** should log meals correctly when given a date qualifier (yesterday vs today), retrieve historical logs across phrasings, and on the today-query reply demonstrate awareness of time-of-day plus what was eaten and what's still missing
**Dimensions:** log-correctness, historical-query-retrieval, time-and-intake-awareness, tone, language-consistency

1. User: "אתמול אכלתי 100 גרם חזה עוף"
   Probes for: does the bot route this as a yesterday-log (not today)? does the HITL preview show the right date?
   *(expect: interrupt)*
   Resume: "כן"

2. User: "אכלתי 50 גרם אורז"
   Probes for: does the bot default this to today and log it correctly?
   *(expect: interrupt)*
   Resume: "כן"

3. User: "מה אכלתי אתמול"
   Probes for: does the bot retrieve yesterday's actual logged data (the chicken from turn 1)?
   *(expect: final)*

4. User: "מה אכלתי השבוע"
   Probes for: does the bot return logs across multiple days (covering both yesterday and today)?
   *(expect: final)*

5. User: "מה אכלתי היום"
   Probes for: in the today reply, does the bot reference the current time-of-day, what's been eaten so far (the rice from turn 2), AND what's still missing relative to the plan? this is the core check — the bot should not just dump the log; it should contextualize it against time and remaining budget.
   *(expect: final)*
