import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Construct path relative to this file
# src/database.py -> src -> root -> data -> nutrition.db
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "nutrition.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

# check_same_thread=False is needed for SQLite in multithreaded envs (like some web servers), 
# though for CLI agents it's less critical, good practice.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db_session() -> Session:
    """Returns a new database session."""
    return SessionLocal()
