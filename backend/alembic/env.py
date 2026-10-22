from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.db.session import Base, db_url as app_db_url

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    # Programmatic callers (tests, run_migrations) may override via config.attributes
    return config.attributes.get("sqlalchemy_url") or app_db_url


def run_migrations_offline() -> None:
    url = _url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=url.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection")
    if connectable is None:
        connectable = create_engine(_url(), poolclass=pool.NullPool)
        own = True
    else:
        own = False
    if hasattr(connectable, "connect") and not hasattr(connectable, "execute"):
        # pytest-alembic hands over an Engine
        conn = connectable.connect()
        own_conn = True
    else:
        conn = connectable if not own else connectable.connect()
        own_conn = own
    try:
        context.configure(
            connection=conn,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=conn.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()
        if own_conn:
            conn.commit()
    finally:
        if own_conn:
            conn.close()
        if own:
            connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
