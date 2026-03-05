import os
import sys
from logging.config import fileConfig

from alembic import context
from alembic.operations.ops import AlterColumnOp, MigrationScript
from sqlalchemy import engine_from_config, pool

# Add project root to sys.path so src.* imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from src.database import SYNC_DATABASE_URL  # noqa: E402
from src.models import Base  # noqa: E402, F401 — registers all models with metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from our project config (never hardcoded in alembic.ini)
config.set_main_option("sqlalchemy.url", SYNC_DATABASE_URL)

target_metadata = Base.metadata


def _strip_nullable_only_ops(
    context, revision, directives: list[MigrationScript]
):
    """SQLite workaround: remove false-positive nullable changes from autogenerate.

    SQLite doesn't report column nullable accurately, so Alembic flags phantom
    drift on nullable columns. This strips AlterColumnOp where the only change
    is modify_nullable (no type or default change).

    Safe to remove when migrating to PostgreSQL/Supabase.
    """
    for directive in directives:
        if directive.upgrade_ops:
            directive.upgrade_ops.ops = [
                op for op in directive.upgrade_ops.ops
                if not (
                    isinstance(op, AlterColumnOp)
                    and op.modify_nullable is not None
                    and op.modify_type is None
                    and op.modify_server_default is False
                )
            ]


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL without connecting)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
        process_revision_directives=_strip_nullable_only_ops,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connects to the database)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,
            process_revision_directives=_strip_nullable_only_ops,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
