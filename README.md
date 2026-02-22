# 🏋️ FitPal AI Agent

FitPal is an intelligent AI fitness and nutrition coach designed to bridge the gap between traditional meal planning and the friction of daily logging. Built on the **LangGraph** framework, the agent acts as a stateful companion that understands natural language, tracks macronutrients (Protein, Carbs, Fats) and Calories in real-time, and provides personalized feedback.

**Mission**: To make rigid nutrition plans flexible and easy to follow through effortless natural language interaction—logging food should feel like texting a friend.

---

## 🌟 Core Features

- **Natural Language Parsing**: Just type "I had 200g of chicken and a banana" and FitPal automatically extracts the foods and quantities using structured Pydantic models.
- **Accurate Nutrition Data**: Uses a local SQLite database for accurate macronutrient calculations (`data/nutrition.db`), avoiding LLM "hallucinations" of calorie counts.
- **Stateful Daily Tracking**: Maintains your daily totals in short-term memory (LangGraph state) and persists confirmed logs to a database.
- **Context-Aware Reasoning**: Ask "How much protein do I have left?" or "What did I eat today?" and FitPal will query your historical logs to answer accurately.
- **Multi-Item Support**: Capable of processing complex meals with multiple items sequentially.

---

## 🏗️ Architecture & Tech Stack

FitPal is built using a modern AI backend stack:

- **Orchestration**: [LangGraph](https://langchain-ai.github.io/langgraph/) (Stateful graphs)
- **LLM Framework**: LangChain 1.x
- **Schema Validation**: Pydantic v2
- **Language Models**: OpenAI (GPT-4o) / Anthropic (Claude 3.5 Sonnet)
- **Database / Storage**: SQLite & SQLAlchemy (with LangGraph SQLite Checkpointer)
- **Package Management**: **`uv`** (strictly enforced for determinism & speed)
- **Language**: Python 3.13+

The core graph logic uses the **Multiple Schemas** pattern (`InputState`, `OutputState`, and internal `AgentState`), ensuring a clean chat interface when exposed via API or LangSmith Studio.

---

## 🚀 Quickstart & Setup

### Prerequisites
Make sure you have [**`uv`**](https://github.com/astral-sh/uv) installed, as it is strictly used for package management.

### 1. Clone & Install Dependencies
Clone the repository and run `uv sync` to create the virtual environment and install all dependencies:
```bash
git clone <your-repo-url>
cd fit_pal
uv sync
```

### 2. Environment Variables
Create a `.env` file in the root directory and add your API keys:
```env
OPENAI_API_KEY=your_openai_api_key
# Or if using Anthropic:
# ANTHROPIC_API_KEY=your_anthropic_api_key

# Global LLM Configuration (Provides defaults for NODE_CONFIGS in src/config.py)
LLM_PROVIDER=openai
LLM_MODEL_NAME=gpt-4o

# Optional: Enable LangSmith Tracing
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_PROJECT=fit_pal
```

### 3. Initialize the Database
The project comes with a script to populate the local `nutrition.db` SQLite database from the provided CSV file:
```bash
uv run src/scripts/ingest_simple_db.py
```

---

## 🖥️ How to Run the Agent Using LangSmith Studio

LangSmith Studio provides the best developer experience for viewing the state execution, debugging, and interacting with the FitPal chat agent locally.

1. **Verify `langgraph-cli` is installed**:
   It should be installed automatically as a development dependency via `uv`.

2. **Start the local Studio development server**:
   From the root directory of the project, run:
   ```bash
   uv run langgraph dev
   ```

3. **Open the Studio Interface**:
   The terminal will output a URL (usually `http://127.0.0.1:2024`). Open this link in your browser.

4. **Interact with FitPal**:
   Because FitPal uses LangGraph's "Multiple Schemas" pattern (defining an `InputState` containing only `messages`), the Studio UI will automatically render a **Chat Box** instead of a complex JSON form on the right-hand panel.
   - Simply type your query in the chat box. Example: `I just had 50g of oats and two medium eggs.`
   - Press **Send**.
   - You can watch the graph execute step-by-step through the `input_parser` ➔ `food_search` ➔ `agent_selection` ➔ `calculate_log` ➔ `response`.

---

## 🗃️ Database Schema

FitPal utilizes two primary tables in SQLite:
- **Food Database**: ~335 common items with verified macros (per 100g). Includes Calories, Protein, Carbs, and Fats.
- **Daily Logs**: Stores confirmed food entries tagged by date/timestamp. Used to aggregate your running daily totals.

---

## 📖 Further Reading

For detailed system requirements, node responsibilities, state schema structures, and development rules, please refer to:
- [`PRD.md`](PRD.md)
- [`.agent/rules/main_rule.md`](.agent/rules/main_rule.md)
