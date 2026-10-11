"""Run only with compose.test.yaml, using disposable PostgreSQL/Redis volumes."""

import os
import uuid

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import text

from app.config import get_settings
from app.database import make_engine
from app.main import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION") != "1",
        reason="Requires isolated Docker stack",
    ),
]


def test_migration_upgrade_downgrade_and_reapply(db_engine):
    # Destructive migration checks may only target the isolated test database.
    settings = get_settings()
    assert settings.app_env == "test"
    assert settings.database_url.get_secret_value().endswith("/suni_test")
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = make_engine(settings)
    with engine.connect() as connection:
        version = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert version == "0010_content_access"
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.check(config)
    from app.migrate import migrate_and_seed

    migrate_and_seed()
    engine.dispose()


def test_real_api_dependencies():
    with TestClient(create_app()) as client:
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["checks"] == {"postgres": "ok", "redis": "ok"}


def test_redis_round_trip():
    with Redis.from_url(get_settings().redis_url.get_secret_value()) as cache:
        key = f"integration:{uuid.uuid4()}"
        try:
            assert cache.set(key, "ok", ex=30)
            assert cache.get(key) == b"ok"
        finally:
            cache.delete(key)


def test_queue_executes_ffmpeg():
    from app.worker import worker_probe

    task = worker_probe.delay()
    result = task.get(timeout=40)
    assert result["status"] == "ok"
    assert result["ffmpeg"].startswith("ffmpeg version")
    task.forget()
