import os

from alembic import context
from sqlalchemy import create_engine

from services.repository import Base


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


provided = context.config.attributes.get("connection")
if provided is not None:
    run(provided)
else:
    engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///./testgen.db"))
    with engine.begin() as connection:
        run(connection)
    engine.dispose()
