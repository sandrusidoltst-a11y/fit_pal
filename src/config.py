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

NODE_CONFIGS = {
    "input_node": {"temperature": 0.0},
    "selection_node": {"temperature": 0.0},
    "response_node": {"temperature": 0.7},
    "default": {"temperature": 0.0}
}

def get_llm_for_node(node_name: str):
    """
    Factory function to get an LLM configured for a specific node.
    """
    config = NODE_CONFIGS.get(node_name, NODE_CONFIGS["default"])
    provider = config.get("provider", GLOBAL_PROVIDER)
    model = config.get("model", GLOBAL_MODEL)
    temperature = config.get("temperature", 0.0)
    
    return init_chat_model(
        model=model,
        model_provider=provider,
        temperature=temperature
    )

def get_openai_api_key() -> str:
    """Retrieve OpenAI API Key from environment."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY not found in environment variables.")
    return key

def get_langchain_api_key() -> str | None:
    """Retrieve LangChain API Key from environment."""
    return os.getenv("LANGCHAIN_API_KEY")
