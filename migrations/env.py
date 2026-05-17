import sys
import os
from logging.config import fileConfig
from sqlalchemy import pool
from alembic import context

sys.path.append(os.getcwd())

from hub.models.database import Base
from hub.models.user import User
from hub.models.task import Task
from hub.models.memory_context import MemoryContext
from hub.models.user_preferences import UserPreferences
from hub.models.conversation_turn import ConversationTurn
from hub.models.audit_log import AuditLog

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine
    from dotenv import load_dotenv

    load_dotenv()

    db_url = os.getenv("DATABASE_URL", "").replace(
        "postgresql+asyncpg://", "postgresql://"
    )

    connectable = create_engine(db_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()