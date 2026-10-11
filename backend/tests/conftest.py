import pytest

from app.config import Settings


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        app_env="test",
        app_secret="a" * 64,
        database_url="postgresql+psycopg://suni:test@localhost/suni",
        redis_url="redis://:test@localhost:6379/0",
        allowed_hosts="testserver,localhost",
    )
