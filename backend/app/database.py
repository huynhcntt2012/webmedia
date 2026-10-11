from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from app.config import Settings


class Base(DeclarativeBase):
    pass


def make_engine(settings: Settings):
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
        hide_parameters=True,
    )


@contextmanager
def session_scope(engine):
    """Commit on success; rollback and close on every error, including flush failures."""
    with Session(engine, expire_on_commit=False) as session, session.begin():
        yield session
