import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.parametrize(
    "override",
    [
        {"app_secret": "short"},
        {"allowed_hosts": "*"},
        {"allowed_hosts": "localhost,"},
        {"database_url": "sqlite:///fake.db"},
        {"redis_url": "redis://localhost/0"},
        {"public_origin": "https://example.com/"},
        {"public_origin": "https://a@b.com"},
        {"readiness_timeout_seconds": 0},
        {"app_env": "production"},
    ],
)
def test_rejects_unsafe_configuration(settings, override):
    values = settings.model_dump() | override
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_secret_values_are_redacted(settings):
    assert "a" * 64 not in repr(settings)
    assert "suni:test" not in repr(settings)


def test_production_requires_https(settings):
    result = Settings(
        _env_file=None,
        **(
            settings.model_dump()
            | {
                "app_env": "production",
                "public_origin": "https://cinema.example.com",
            }
        ),
    )
    assert result.app_env == "production"
