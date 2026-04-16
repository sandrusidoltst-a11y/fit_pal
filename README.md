# FitPal AI Agent

FitPal is an intelligent AI fitness and nutrition coach built on **LangGraph**. Users log food in natural language ("I had 200g of chicken and a banana"); the agent parses intent, looks up macros from a Supabase PostgreSQL database, and maintains a stateful daily log. Also supports personal stats tracking (weight, body fat) and user profile management.

**Mission**: Make nutrition tracking effortless — logging food should feel like texting a friend.

---

## Core Features

- **Natural Language Parsing**: Type "I had 200g of chicken and a banana" — FitPal extracts foods and quantities using Pydantic structured output.
- **Accurate Nutrition Data**: Looks up macros from a Supabase PostgreSQL database (~335 common items). Off-menu foods are estimated via LLM and persisted for reuse.
- **Stateful Daily Tracking**: Persists confirmed logs to Supabase. Query your history with "What did I eat today?"
- **Multi-Item Support**: Processes complex meals with multiple items sequentially via loop-back graph routing.
- **HITL Confirmation**: Previews macros before committing — confirm, reject, or edit via natural language.
- **Personal Stats**: Log body measurements ("I weigh 74kg", "body fat 15%") tracked over time.
- **Telegram Bot**: Chat with FitPal via Telegram — passphrase access control, onboarding, and full HITL support.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph (StateGraph, async) |
| LLM | GPT-4.1-nano (default) / GPT-4o |
| Storage | Supabase PostgreSQL + SQLAlchemy (asyncpg) |
| Bot | aiogram v3 (Telegram, webhook + polling) |
| Deployment | Railway (4 services) + Docker Hub |
| CI/CD | GitHub Actions |
| Package Manager | `uv` (strictly enforced) |
| Language | Python 3.13+ |

---

## Quickstart

### Prerequisites
- [**uv**](https://github.com/astral-sh/uv) installed
- OpenAI API key
- Supabase project (for DB)

### 1. Clone & Install
```bash
git clone <your-repo-url>
cd fit_pal
uv sync
```

### 2. Environment Variables
Create a `.env` file:
```env
OPENAI_API_KEY=your_openai_api_key
SUPABASE_DB_URL=your_supabase_connection_string

# Optional: LangSmith tracing
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_PROJECT=fit-pal-agent
```

### 3. Run with LangGraph Studio
```bash
uv run langgraph dev
```
Open `http://127.0.0.1:2024` in your browser. Type food entries in the chat box and watch the graph execute step-by-step.

---

## Local Bot Development

Test the Telegram bot locally without deploying:

1. **Create a dev bot** via [@BotFather](https://t.me/BotFather) on Telegram
2. **Add to `.env`**:
   ```env
   BOT_TOKEN=<dev-bot-token>
   POLLING_MODE=true
   BOT_PASSPHRASE=<any-passphrase>
   BOT_PASSWORD_SEED=<from-production>
   SUPABASE_URL=<your-supabase-url>
   SUPABASE_SERVICE_KEY=<your-service-role-key>
   BOT_EMAIL_DOMAIN=dev.fitpal.bot
   ```
3. **Terminal 1**: `uv run langgraph dev`
4. **Terminal 2**: `uv run python -m bot.gateway`
5. Open your dev bot on Telegram and send the passphrase

`BOT_EMAIL_DOMAIN=dev.fitpal.bot` creates separate auth users from production, so you can test onboarding with your own Telegram account.

---

## Localization

The bot UI language is set via the `BOT_LANGUAGE` env var.

- Supported: `en` (default), `he`
- Set on **both** the `langgraph-server` and `fitpal-bot` Railway services — they each load the i18n module independently, so a mismatch yields half-translated chats.
- Adding a new user-facing string: add the key to the `Messages` TypedDict in `src/i18n/__init__.py`, then add the same key to both `src/i18n/en.yaml` and `src/i18n/he.yaml`. The startup parity check refuses to boot if any of the three drift apart.
- LLM-generated coach responses are not in the YAML — the response-node system prompt instructs the model to match the user's language automatically.

---

## Testing

```bash
# Unit tests (fast, mocked)
uv run pytest tests/unit/ -v

# Integration tests (real Supabase DB)
uv run pytest tests/integration/ -v

# E2E graph-api tests (full server + real LLM)
uv run pytest tests/graph_api/ -v -s
```

---

## Further Reading

- [`PRD.md`](PRD.md) — Full requirements, features, and specs
- [`CLAUDE.md`](CLAUDE.md) — Project context, architecture patterns, and development rules
- [`docs/phase3-deployment-plan.md`](docs/phase3-deployment-plan.md) — Deployment guide
