
# Phase 2: Core Focus Areas (1-Sentence Summaries)

- **User Isolation**: We must assign unique User IDs to all logs and state checkpoints to prevent different users' data from mixing together.
- **Timezones**: We need to track user-specific timezones instead of relying on UTC to ensure "daily" nutritional totals reset at the correct local midnight.
- **Database Migrations**: We should adopt a migration tool like Alembic to safely update our database schema without wiping existing user data.
- **Async Preparedness**: We need to refactor database operations to be asynchronous so they don't block requests when multiple users interact simultaneously.
- **Structured Targets**: We must store daily dietary goals as strict database fields rather than free text to allow the agent to perform exact math.
- **Correction Workflow**: We need to implement an edit/delete feature for past entries so user typos or agent mistakes don't permanently ruin daily totals.
- **Meal Context**: We should actively utilize meal tags (like breakfast or dinner) so the agent can provide proactive, time-aware advice.
- **Custom Foods**: We must isolate user-created food entries into private tables to prevent spelling mistakes from polluting the global food database.
- **Unit Normalization**: We must strictly enforce a standard unit of measurement (like grams) for all entries to keep macro calculations mathematically reliable.
- **Context Limits**: We need a system to trim or summarize long chat histories to prevent hitting LLM token limits and accumulating high API costs.
- **Configurations**: We must extract LLM choices and API settings into configuration files instead of hardcoding them, allowing for easier testing and environment management.
