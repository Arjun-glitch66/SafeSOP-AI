"""Alembic environment. The engine comes from app.db (DATABASE_URL or the SQLite file), so
`alembic upgrade head` on the command line and init_db() at startup migrate the same database.
`alembic upgrade head --sql` prints the SQL for DATABASE_URL's dialect without connecting."""
from alembic import context

from app import config

if context.is_offline_mode():
    context.configure(url=config.database_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    from app.db import engine as app_engine

    connectable = context.config.attributes.get("engine") or app_engine()
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None,
                          render_as_batch=connection.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()
        connection.commit()
