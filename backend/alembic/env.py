from alembic import context

from app.database import Base, get_engine
from app import models  # Register model metadata.

target_metadata = Base.metadata

if context.is_offline_mode():
    raise RuntimeError("Use online migrations; database credentials are never rendered into SQL output.")
else:
    def run_migrations(connection):
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

    # Integration tests inject an explicitly selected isolated connection.
    # Ordinary CLI commands retain the existing application configuration.
    supplied_connection = context.config.attributes.get('connection')
    if supplied_connection is not None:
        run_migrations(supplied_connection)
    else:
        with get_engine().connect() as connection:
            run_migrations(connection)
