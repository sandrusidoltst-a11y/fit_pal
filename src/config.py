import os
from dotenv import load_dotenv

from langchain.chat_models import init_chat_model

# Load environment variables from .env file
load_dotenv()

# Project Root (calculated relative to this file: src/config.py -> src -> root)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "nutrition.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

GLOBAL_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
GLOBAL_MODEL = os.getenv("LLM_MODEL_NAME", "gpt-4o")

# LLM Configuration Hierarchy
# 1. Node-Specific Settings (NODE_CONFIGS): Highest priority. If a node defines a parameter (e.g., 'temperature', 'provider', 'max_tokens'), it takes precedence.
# 2. Global Defaults (.env / GLOBAL_* variables): If a parameter like 'model' or 'provider' is missing from the node config, it falls back to LLM_PROVIDER or LLM_MODEL_NAME.
# 3. Hardcoded Defaults: If entirely missing, safe minimums (like temperature=0.0) are applied in the fallback chain.
NODE_CONFIGS = {
    "input_node": {"temperature": 0.0},
    "selection_node": {"temperature": 0.0},
    "response_node": {"temperature": 0.7},
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
    params = {
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
