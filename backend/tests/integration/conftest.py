import os

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.bootstrap_db import provision_roles
from app.config import get_settings
from app.database import make_engine
from app.migrate import migrate_and_seed


@pytest.fixture(scope="session", autouse=True)
def db_engine():
    if os.getenv("RUN_INTEGRATION") != "1":
        pytest.skip("Requires isolated Docker stack")
    settings = get_settings()
    assert settings.app_env == "test"
    assert make_url(settings.database_url.get_secret_value()).database == "suni_test"
    admin_url = os.environ["BOOTSTRAP_DATABASE_URL"]
    assert make_url(admin_url).database == "suni_test"
    # Reproduce the existing stage 01 volume: version table owned by the bootstrap role.
    with psycopg.connect(admin_url.replace("postgresql+psycopg://", "postgresql://", 1)) as conn:
        assert not conn.execute("SELECT to_regclass('public.alembic_version')").fetchone()[0]
        conn.execute("CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY)")
        conn.execute("INSERT INTO alembic_version VALUES ('0001_bootstrap')")
    for _ in range(2):
        provision_roles(admin_url, os.environ["MIGRATOR_PASSWORD"], os.environ["RUNTIME_PASSWORD"])
    migrate_and_seed()
    engine = make_engine(settings)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT current_database()")) == "suni_test"
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine):
    # Outer transaction isolates test data even when session.commit() is called.
    with db_engine.connect() as connection:
        outer = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        outer.rollback()
