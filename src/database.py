from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import DATABASE_URL

# --- Async infrastructure (service layer + graph nodes) ---
# expire_on_commit=False is REQUIRED: prevents MissingGreenlet errors when
# accessing ORM attributes after commit() in async context.
async_engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)


def get_async_db_session() -> AsyncSession:
    """Returns a new async database session (use as async context manager)."""
    return AsyncSessionLocal()


# --- Sync infrastructure (LangChain tools + ETL scripts) ---
# Derive sync URL by stripping the +aiosqlite dialect suffix.
SYNC_DATABASE_URL = DATABASE_URL.replace("+aiosqlite", "")
engine = create_engine(SYNC_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db_session() -> Session:
    """Returns a new sync database session (for tools and scripts)."""
    return SessionLocal()
