import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Project Root (calculated relative to this file: src/config.py -> src -> root)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "nutrition.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

def get_openai_api_key() -> str:
    """Retrieve OpenAI API Key from environment."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY not found in environment variables.")
    return key

def get_langchain_api_key() -> str | None:
    """Retrieve LangChain API Key from environment."""
    return os.getenv("LANGCHAIN_API_KEY")
