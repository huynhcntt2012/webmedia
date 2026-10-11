import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import session_scope
from app.migrate import migrate_and_seed
from app.models import Comic, ContentDevice, ContentGrant, Movie, User
from tests.integration.test_admin_catalogue import admin_api  # noqa: F401
from tests.integration.test_admin_comics import comics_api  # noqa: F401
from tests.integration.test_media_pipeline import media_api, video  # noqa: F401
from tests.integration.test_playback import playable  # noqa: F401
from tests.integration.test_reader import readable  # noqa: F401

pytestmark = pytest.mark.integration
PASSWORD = "Content test password 123!"


def viewer(admin, email="content@example.com", register=True):
    c = TestClient(admin.app)
    c.headers["Origin"] = admin.headers["Origin"]
    c.headers["X-CSRF-Token"] = c.get("/auth/csrf").json()["csrf_token"]
    if register:
        assert (
            c.post(
                "/auth/register",
                json={
                    "email": email,
                    "display_name": "Content viewer",
                    "password": PASSWORD,
                },
            ).status_code
            == 202
        )
    assert c.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    return c


def grant(admin, c, **values):
    uid = c.get("/auth/me").json()["user"]["id"]
    result = admin.post(
        "/admin/content-grants",
        json={
            "user_id": uid,
            "plan_code": "vip",
            "days": 1,
            "device_limit": 2,
            **values,
        },
    )
    assert result.status_code == 201, result.text
    return result.json()["id"]


def test_paid_hls_grant_revoke_expiry_and_hierarchy(playable, db_engine):  # noqa: F811
    admin, ep, job, movie, _ = playable
    c = viewer(admin)
    urls = [
        f"/playback/episodes/{ep}",
        f"/playback/jobs/{job}/media/master.m3u8",
        f"/playback/jobs/{job}/media/360p/index.m3u8",
        f"/playback/jobs/{job}/media/360p/segment_00000.ts",
    ]
    with session_scope(db_engine) as db:
        db.get(Movie, movie).required_plan_code = "vip"
    assert all(c.get(url).status_code == 403 for url in urls)
    identifier = grant(admin, c)
    assert all(c.get(url).status_code == 200 for url in urls)
    with session_scope(db_engine) as db:
        db.get(Movie, movie).required_plan_code = "premium"
    assert c.get(urls[0]).status_code == 403
    premium = grant(admin, c, plan_code="premium")
    assert c.get(urls[-1]).status_code == 200
    assert admin.delete(f"/admin/content-grants/{premium}").status_code == 204
    assert c.get(urls[-1]).status_code == 403
    with session_scope(db_engine) as db:
        db.get(Movie, movie).required_plan_code = "vip"
        row = db.get(ContentGrant, uuid.UUID(identifier))
        row.starts_at = datetime.now(UTC) - timedelta(days=2)
        row.expires_at = datetime.now(UTC) - timedelta(days=1)
    assert c.get(urls[-1]).status_code == 403
    assert c.get("/content/access").json()["plan"] == "free"


def test_atomic_device_limit_owner_revoke_and_idle_expiry(readable, db_engine):  # noqa: F811
    admin, _, ch, _, pages = readable
    base = f"/reader/chapters/{ch['id']}"
    image = base + f"/pages/{pages[0]['id']}/image"
    clients = [viewer(admin)] + [viewer(admin, register=False) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda c: c.get(image).status_code, clients))
    assert sorted(results) == [200, 200, 403]
    denied = clients[results.index(403)]
    active = denied.get("/content/devices").json()["items"]
    assert len(active) == 2
    other = viewer(admin, "other-content@example.com")
    path = f"/content/devices/{active[0]['id']}"
    assert other.delete(path).status_code == 404
    assert denied.delete(path, headers={"X-CSRF-Token": "invalid"}).status_code == 403
    assert denied.delete(path).status_code == 204
    assert denied.get(image).status_code == 200
    assert sorted(c.get("/auth/me").status_code for c in clients) == [200, 200, 401]
    with session_scope(db_engine) as db:
        for row in db.scalars(select(ContentDevice)):
            row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    fourth = viewer(admin, register=False)
    assert fourth.get(image).status_code == 200
    assert len(fourth.get("/content/devices").json()["items"]) == 1


def test_grant_admin_only_csrf_image_revocation_and_reduced_limit(readable, db_engine):  # noqa: F811
    admin, comic, ch, _, pages = readable
    c = viewer(admin)
    second = viewer(admin, register=False)
    third = viewer(admin, register=False)
    url = f"/reader/chapters/{ch['id']}/pages/{pages[0]['id']}/image"
    uid = c.get("/auth/me").json()["user"]["id"]
    data = {"user_id": uid, "plan_code": "vip", "days": 1, "device_limit": 3}
    assert c.post("/admin/content-grants", json=data).status_code == 403
    assert (
        admin.post(
            "/admin/content-grants", json=data, headers={"X-CSRF-Token": "invalid"}
        ).status_code
        == 403
    )
    identifier = grant(admin, c, device_limit=3)
    for client in [c, second, third]:
        assert client.get(url).status_code == 200
    assert admin.delete(f"/admin/content-grants/{identifier}").status_code == 204
    assert [client.get(url).status_code for client in [c, second, third]] == [200, 200, 403]
    with session_scope(db_engine) as db:
        db.get(Comic, uuid.UUID(comic["id"])).required_plan_code = "vip"
        db.get(User, uuid.UUID(uid)).plan_code = "premium"
    assert c.get(url).status_code == 403
    grant(admin, c)
    assert c.get(url).status_code == 200
    assert admin.get(f"/admin/content-grants?user_id={uid}").status_code == 200
    assert c.get(f"/admin/content-grants?user_id={uid}").status_code == 403


def test_content_migration_rollback_reapply(db_engine):
    config = Config("alembic.ini")
    command.downgrade(config, "0009_payments")
    migrate_and_seed()
    command.check(config)
