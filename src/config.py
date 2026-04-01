from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING, Any

import structlog
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

# Load environment variables from .env file
load_dotenv()

logger = structlog.get_logger(__name__)

# Project Root (calculated relative to this file: src/config.py -> src -> root)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "nutrition.db")
DEFAULT_DEV_USER_ID = "fbeeb45f-d728-4c7c-9e6d-7b9b41685da7"
DEFAULT_DEV_PROFILE = {
    "name": "Dev User",
    "height_cm": 175.0,
    "age": 25,
    "gender": "male",
}


def get_user_id(config: RunnableConfig | None) -> str:
    """Extract user_id from LangGraph config, falling back to dev default.

    Priority chain:
    1. Production: auth handler populates langgraph_auth_user (Supabase UUID).
    2. Dev/Studio: manual config["configurable"]["user_id"], validated as UUID.
       Studio injects its own non-UUID user_id for Store namespacing — ignored.
    3. Fallback: DEFAULT_DEV_USER_ID.
    """
    if config:
        # Production path: auth handler sets this
        auth_user = config["configurable"].get("langgraph_auth_user")
        if auth_user:
            return auth_user["identity"]
        # Dev/Studio path: validate as UUID before accepting
        user_id = config["configurable"].get("user_id", DEFAULT_DEV_USER_ID)
        try:
            uuid.UUID(user_id)
            return user_id
        except ValueError:
            logger.warning("Non-UUID user_id in config (likely Studio-injected), falling back to default",
                           received=user_id, fallback=DEFAULT_DEV_USER_ID)
            return DEFAULT_DEV_USER_ID
    logger.warning("No config provided, falling back to DEFAULT_DEV_USER_ID", user_id=DEFAULT_DEV_USER_ID)
    return DEFAULT_DEV_USER_ID


def get_user_profile(config: RunnableConfig | None) -> dict:
    """Extract user_profile from config, falling back to dev default.

    Priority chain:
    1. Production: bot injects real profile from DB into config.
    2. Dev/Studio: falls back to DEFAULT_DEV_PROFILE.

    Always returns a profile dict so nodes never need None-checks.
    """
    if config:
        profile = config["configurable"].get("user_profile")
        if profile:
            return profile
    logger.warning("No user_profile in config, falling back to DEFAULT_DEV_PROFILE")
    return DEFAULT_DEV_PROFILE


_supabase_url = os.getenv("SUPABASE_DB_URL")
if _supabase_url:
    DATABASE_URL = _supabase_url.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

logger.info("Database backend resolved", backend="asyncpg (Supabase)" if _supabase_url else "sqlite (local)")

GLOBAL_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
GLOBAL_MODEL = os.getenv("LLM_MODEL_NAME", "gpt-4.1-nano")

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
