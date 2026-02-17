from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from src.config import DATABASE_URL

# check_same_thread=False is needed for SQLite in multithreaded envs (like some web servers), 
# though for CLI agents it's less critical, good practice.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db_session() -> Session:
    """Returns a new database session."""
    return SessionLocal()
