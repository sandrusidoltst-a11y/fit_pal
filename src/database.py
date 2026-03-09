import ssl as _ssl

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import DATABASE_URL

# --- Async infrastructure (service layer + graph nodes) ---
# expire_on_commit=False is REQUIRED: prevents MissingGreenlet errors when
# accessing ORM attributes after commit() in async context.
#
# For asyncpg (Supabase Postgres): pass an explicit SSLContext via connect_args
# to prevent asyncpg from calling pathlib.resolve() → os.getcwd() when searching
# for ~/.postgresql/ client certs. That sync call triggers BlockingError in
# LangGraph's ASGI server (blockbuster).
_engine_kwargs: dict = {}
if "asyncpg" in DATABASE_URL:
    _ctx = _ssl.create_default_context()
    _ctx.check_hostname = False
    _ctx.verify_mode = _ssl.CERT_NONE
    _engine_kwargs["connect_args"] = {"ssl": _ctx}

async_engine = create_async_engine(DATABASE_URL, **_engine_kwargs)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)


def get_async_db_session() -> AsyncSession:
    """Returns a new async database session (use as async context manager)."""
    return AsyncSessionLocal()
