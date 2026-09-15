"""Alembic environment.

Migrations run through the app's own engine, so they use exactly the same
connection logic (SQLite locally; Azure SQL with managed-identity tokens and
resume retry in Azure) instead of a separately configured URL.
"""
from alembic import context

from database import Base, engine

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout (``alembic upgrade head --sql``) without connecting."""
    context.configure(
        url=engine.url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=engine.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite can't ALTER most constraints; batch mode rebuilds tables instead.
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
