from __future__ import annotations

import os
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

# Load environment variables from .env file
load_dotenv()

logger = structlog.get_logger(__name__)

# Project Root (calculated relative to this file: src/config.py -> src -> root)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "nutrition.db")

# All POC users are in Israel. Hardcoded until per-user timezone lands on user_profile.
USER_TIMEZONE = ZoneInfo("Asia/Jerusalem")

# Single-coach POC fallback. Maps to Dolev's production Telegram user
# (275939731@telegram.fitpal.bot). When we extend to multiple coaches,
# replace this constant with a coaches-table lookup.
DEFAULT_COACH_ID = uuid.UUID("71a8c873-c6bd-498e-a6ca-bd27d6118329")


def serialize_timestamp(ts: datetime | None) -> str | None:
    """Serialize a UTC-stored datetime to Israel-local ISO string for LLM consumption."""
    if ts is None:
        return None
    return ts.astimezone(USER_TIMEZONE).isoformat()


def day_bounds_utc(target_date: date, tz: ZoneInfo = USER_TIMEZONE) -> tuple[datetime, datetime]:
    """Return [start_utc, end_utc) UTC bounds for ``target_date`` in ``tz``.

    Midnight in ``tz`` is unambiguous on DST transition days, so this is safe
    to call for any local date without DST hour-folding concerns.
    """
    start_local = datetime.combine(target_date, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def timestamp_in_local_day(column, target_date: date, tz: ZoneInfo = USER_TIMEZONE):
    """SQLAlchemy predicate: ``column`` falls within the local-tz day for ``target_date``.

    Use this instead of ``func.date(column) == target_date`` for any TIMESTAMPTZ
    column whose intended day-bucketing is in user-local time. ``func.date`` on a
    TIMESTAMPTZ extracts the date in the DB session timezone (UTC on Supabase),
    which silently drops late-night-local entries from "today" queries.
    """
    start, end = day_bounds_utc(target_date, tz)
    return (column >= start) & (column < end)


def timestamp_in_local_day_range(
    column, start_date: date, end_date: date, tz: ZoneInfo = USER_TIMEZONE
):
    """SQLAlchemy predicate: ``column`` falls within ``[start_date, end_date]`` inclusive in ``tz``.

    The end bound is converted to the *next* day's UTC start, preserving the
    inclusive-end semantics of the original ``func.date(...) <= end_date`` form.
    """
    start, _ = day_bounds_utc(start_date, tz)
    _, end = day_bounds_utc(end_date, tz)
    return (column >= start) & (column < end)


_supabase_url = os.getenv("SUPABASE_DB_URL")
if _supabase_url:
    DATABASE_URL = _supabase_url.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

logger.info("Database backend resolved", backend="asyncpg (Supabase)" if _supabase_url else "sqlite (local)")

# NOTE: The default below only applies locally. Production reads LLM_MODEL_NAME
# from Railway env vars on the `langgraph-server` service — changing the default
# here does NOT affect prod. To change the prod model, update LLM_MODEL_NAME in
# the Railway dashboard (or `railway variables --set LLM_MODEL_NAME=...`).
GLOBAL_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
GLOBAL_MODEL = os.getenv("LLM_MODEL_NAME", "gpt-5.4-nano")

logger.info("LLM config loaded", provider=GLOBAL_PROVIDER, model=GLOBAL_MODEL)

# LLM Configuration Hierarchy
# 1. Node-Specific Settings (NODE_CONFIGS): Highest priority. If a node defines a parameter (e.g., 'temperature', 'provider', 'max_tokens'), it takes precedence.
# 2. Global Defaults (.env / GLOBAL_* variables): If a parameter like 'model' or 'provider' is missing from the node config, it falls back to LLM_PROVIDER or LLM_MODEL_NAME.
# 3. Hardcoded Defaults: If entirely missing, safe minimums (like temperature=0.0) are applied in the fallback chain.
NODE_CONFIGS = {
    "input_node": {"temperature": 0.0},
    "selection_node": {"temperature": 0.0},
    "estimation_node": {"temperature": 0.0},
    "confirmation_node": {"temperature": 0.0},
    "response_node": {"temperature": 0.7},
    "personal_stats_node": {"temperature": 0.0},
    "default": {"temperature": 0.0}
}

def get_llm_for_node(node_name: str):
    """
    Factory function to get an LLM configured for a specific node.
    
    This unpacks the merged node configuration (**kwargs) directly into LangChain's `init_chat_model` API.
    Common configurable parameters include: `model`, `model_provider`, `temperature`, `max_tokens`, `stop`, `timeout`, and `max_retries`.
    
    For a full list of valid parameters supported by each provider, see the official LangChain documentation:
    🔗 https://python.langchain.com/docs/how_to/chat_models_universal_init/
    """
    # Base defaults
    params: dict[str, Any] = {
        "model_provider": GLOBAL_PROVIDER,
        "model": GLOBAL_MODEL,
        "temperature": 0.0
    }
    
    # Overlay node specific config
    node_config = NODE_CONFIGS.get(node_name, NODE_CONFIGS.get("default", {}))
    params.update(node_config)
    
    # Map 'provider' to init_chat_model's expected argument 'model_provider'
    if "provider" in params:
        params["model_provider"] = params.pop("provider")
        
    return init_chat_model(**params)

def get_openai_api_key() -> str:
    """Retrieve OpenAI API Key from environment."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY not found in environment variables.")
    return key

def get_langchain_api_key() -> str | None:
    """Retrieve LangChain API Key from environment."""
    return os.getenv("LANGCHAIN_API_KEY")
