import os
import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import delete, select, update

from app.config import Settings, get_settings
from app.database import session_scope
from app.main import create_app
from app.migrate import migrate_and_seed
from app.models import AuthSession, RefreshToken, User
from app.security import digest, verify_password

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION") != "1", reason="Requires isolated Docker stack"
    ),
]
PASSWORD = "Suni test password 123!"


def restore_cookies(browser, values):
    browser.cookies.clear()
    for name, value in values.items():
        browser.cookies.set(name, value, domain="testserver.local", path="/")


@pytest.fixture
def auth_app(db_engine):
    settings = Settings(
        _env_file=None,
        **(
            get_settings().model_dump()
            | {
                "database_url": os.environ["RUNTIME_DATABASE_URL"],
                "app_secret": secrets.token_hex(32),
                "auth_ip_limit": 5000,
                "auth_account_limit": 5000,
            }
        ),
    )
    app = create_app(settings)
    yield app
    # Test-only data is removed through the migrator, not runtime privileges.
    with session_scope(db_engine) as db:
        db.execute(delete(User))


@pytest.fixture
def client(auth_app):
    with TestClient(auth_app) as browser:
        browser.headers["Origin"] = auth_app.state.settings.public_origin
        csrf = browser.get("/auth/csrf")
        assert csrf.status_code == 200
        browser.headers["X-CSRF-Token"] = csrf.json()["csrf_token"]
        yield browser


def register(client, email=None):
    email = email or f"{uuid.uuid4()}@example.com"
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "display_name": "Người dùng kiểm thử",
        },
    )
    assert response.status_code == 202, response.text
    return email


def login(client, email):
    response = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response


def test_registration_hash_default_and_duplicate_indistinguishable(client, db_engine):
    email = register(client)
    response = client.post(
        "/auth/register",
        json={"email": email.upper(), "password": PASSWORD, "display_name": "Duplicate"},
    )
    assert response.status_code == 202
    assert (
        response.json()
        == client.post(
            "/auth/register",
            json={
                "email": f"{uuid.uuid4()}@example.com",
                "password": PASSWORD,
                "display_name": "New",
            },
        ).json()
    )
    with session_scope(db_engine) as db:
        user = db.scalar(select(User).where(User.email == email))
        assert verify_password(PASSWORD, user.password_hash)
        assert user.role == "user" and user.plan_code == "free"
        assert user.display_name == "Người dùng kiểm thử"


def test_login_me_cookie_flags_and_rbac(client):
    email = register(client)
    response = login(client, email)
    assert "password" not in response.text and "token" not in response.text
    for cookie in response.headers.get_list("set-cookie"):
        assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie
    user = client.get("/auth/me").json()["user"]
    assert user["email"] == email and user["role"] == "user"
    assert client.get("/auth/me?user_id=" + str(uuid.uuid4())).json()["user"]["id"] == user["id"]
    assert client.get("/admin/check").status_code == 403
    client.cookies.clear()
    assert client.get("/auth/me").status_code == 401
    assert client.get("/admin/check").status_code == 401


def test_wrong_password_unknown_and_disabled_have_same_response(client, db_engine):
    email = register(client)
    wrong = client.post("/auth/login", json={"email": email, "password": "Incorrect password 123"})
    missing = client.post(
        "/auth/login", json={"email": "missing@example.com", "password": PASSWORD}
    )
    with session_scope(db_engine) as db:
        db.execute(update(User).where(User.email == email).values(is_active=False))
    disabled = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert wrong.status_code == missing.status_code == disabled.status_code == 401
    assert wrong.json() == missing.json() == disabled.json()


def test_admin_privilege_and_disable_take_effect_without_new_jwt(client, db_engine):
    email = register(client)
    login(client, email)
    with session_scope(db_engine) as db:
        db.execute(update(User).where(User.email == email).values(role="admin"))
    assert client.get("/admin/check").status_code == 200
    with session_scope(db_engine) as db:
        db.execute(update(User).where(User.email == email).values(role="user"))
    assert client.get("/admin/check").status_code == 403
    with session_scope(db_engine) as db:
        db.execute(update(User).where(User.email == email).values(is_active=False))
    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/refresh").status_code == 401


def test_rotation_hash_only_and_reuse_revokes_family(client, auth_app, db_engine):
    login(client, register(client))
    old = client.cookies.get("suni_refresh")
    with session_scope(db_engine) as db:
        stored = db.get(RefreshToken, digest(old))
        assert stored and stored.token_hash != old
    assert client.post("/auth/refresh").status_code == 200
    assert client.cookies.get("suni_refresh") != old
    saved = dict(client.cookies)
    with TestClient(auth_app) as replay:
        replay.headers.update(client.headers)
        restore_cookies(replay, saved | {"suni_refresh": old})
        assert replay.post("/auth/refresh").status_code == 401
    assert client.get("/auth/me").status_code == 401


def test_concurrent_refresh_is_single_use_and_replay_revokes(client, auth_app):
    login(client, register(client))
    cookies = dict(client.cookies)
    headers = dict(client.headers)

    def rotate(_):
        with TestClient(auth_app) as browser:
            browser.headers.update(headers)
            restore_cookies(browser, cookies)
            result = browser.post("/auth/refresh")
            return result.status_code, dict(browser.cookies)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(rotate, range(2)))
    assert sorted(result[0] for result in results) == [200, 401]
    restore_cookies(client, next(c for status, c in results if status == 200))
    assert client.get("/auth/me").status_code == 401


def test_logout_revokes_existing_access_and_refresh(client, auth_app):
    login(client, register(client))
    stolen = dict(client.cookies)
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401
    restore_cookies(client, stolen)
    assert client.post("/auth/refresh").status_code == 401
    assert client.get("/auth/me").status_code == 401


def test_logout_all_scoped_to_current_user(client, auth_app):
    first = register(client)
    login(client, first)
    saved = dict(client.cookies)
    login(client, first)
    assert client.post("/auth/logout-all").status_code == 204
    restore_cookies(client, saved)
    assert client.get("/auth/me").status_code == 401


def test_logout_revokes_access_even_without_refresh_cookie(client):
    login(client, register(client))
    saved = dict(client.cookies)
    client.cookies.delete("suni_refresh", domain="testserver.local", path="/")
    assert client.post("/auth/logout").status_code == 204
    restore_cookies(client, saved)
    assert client.get("/auth/me").status_code == 401


def test_logout_all_cannot_revoke_another_user(client, auth_app):
    login(client, register(client))
    first = dict(client.cookies)
    second_email = register(client)
    login(client, second_email)
    second = dict(client.cookies)
    restore_cookies(client, first)
    assert client.post("/auth/logout-all").status_code == 204
    restore_cookies(client, second)
    assert client.get("/auth/me").json()["user"]["email"] == second_email


def test_expired_access_refresh_and_absolute_session_expiry(client, db_engine, auth_app):
    login(client, register(client))
    raw = client.cookies.get("suni_access")
    secret = auth_app.state.settings.app_secret.get_secret_value()
    claims = jwt.decode(raw, secret, algorithms=["HS256"], audience="suni-web")
    expired = jwt.encode(
        claims | {"exp": int(datetime.now(UTC).timestamp()) - 1}, secret, algorithm="HS256"
    )
    client.cookies.set("suni_access", expired, domain="testserver.local", path="/")
    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/refresh").status_code == 200
    with session_scope(db_engine) as db:
        db.execute(update(AuthSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    assert client.post("/auth/refresh").status_code == 401


@pytest.mark.parametrize("attack", ["origin", "missing", "mismatch", "forged"])
def test_csrf_and_origin_required(client, attack):
    if attack == "origin":
        client.headers["Origin"] = "https://evil.example"
    if attack == "missing":
        del client.headers["X-CSRF-Token"]
    if attack == "mismatch":
        client.headers["X-CSRF-Token"] = "bad"
    if attack == "forged":
        client.cookies.set("suni_csrf", "forged", domain="testserver.local", path="/")
        client.headers["X-CSRF-Token"] = "forged"
    assert (
        client.post(
            "/auth/login", json={"email": "a@example.com", "password": PASSWORD}
        ).status_code
        == 403
    )


def test_limits_cannot_be_bypassed_with_forwarded_headers(client, auth_app):
    auth_app.state.settings.auth_ip_limit = 1
    assert client.post("/auth/logout").status_code == 204
    assert client.post("/auth/logout", headers={"X-Forwarded-For": "9.9.9.9"}).status_code == 429


def test_account_rate_limit(client, auth_app):
    auth_app.state.settings.auth_account_limit = 1
    assert (
        client.post(
            "/auth/login", json={"email": "a@example.com", "password": PASSWORD}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/auth/login", json={"email": "A@example.com", "password": PASSWORD}
        ).status_code
        == 429
    )


def test_redis_failure_fails_closed(client, auth_app, monkeypatch):
    def failed(*args):
        raise RedisConnectionError("private redis address")

    monkeypatch.setattr(auth_app.state.auth_cache, "eval", failed)
    response = client.post("/auth/login", json={"email": "a@example.com", "password": PASSWORD})
    assert response.status_code == 503 and "private redis" not in response.text


def test_mass_assignment_and_validation_never_echo_password(client):
    response = client.post(
        "/auth/register",
        json={
            "email": "a@example.com",
            "password": PASSWORD,
            "display_name": "Test",
            "role": "admin",
            "plan_code": "premium",
        },
    )
    assert response.status_code == 422 and PASSWORD not in response.text
    assert client.post("/auth/login", content=b"x" * 9000).status_code == 413


def test_production_cookie_flags(auth_app):
    auth_app.state.settings.app_env = "production"
    auth_app.state.settings.public_origin = "https://testserver"
    with TestClient(auth_app, base_url="https://testserver") as browser:
        browser.headers["Origin"] = "https://testserver"
        response = browser.get("/auth/csrf")
        browser.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        response = login(browser, register(browser))
        assert browser.cookies.get("__Host-suni_access")
        assert all(
            "Secure" in c and "HttpOnly" in c for c in response.headers.get_list("set-cookie")
        )


def test_stage03_migration_preserves_existing_users(db_engine):
    config = Config("alembic.ini")
    command.downgrade(config, "0002_domain")
    with session_scope(db_engine) as db:
        existing = User(
            email="migration@example.com",
            display_name="Preserve",
            password_hash="$argon2id$fixture",
        )
        db.add(existing)
        db.flush()
        identifier = existing.id
    migrate_and_seed()
    command.check(config)
    with session_scope(db_engine) as db:
        assert db.get(User, identifier).display_name == "Preserve"
        db.execute(delete(User).where(User.id == identifier))
