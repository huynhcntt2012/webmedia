from alembic import context

from app import models  # noqa: F401 -- register the entire domain metadata
from app.config import get_settings
from app.database import Base, make_engine

target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(
        url=get_settings().database_url.get_secret_value(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = make_engine(get_settings())
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
