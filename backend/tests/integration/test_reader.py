import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, select, update

from app.database import session_scope
from app.migrate import migrate_and_seed
from app.models import Comic, ReadingProgress, User
from tests.integration.test_admin_catalogue import admin_api  # noqa: F401
from tests.integration.test_admin_comics import chapter, comic, comics_api, upload  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.fixture
def readable(comics_api, db_engine):  # noqa: F811
    c = comics_api
    row = comic(c, "reader-story")
    ch = chapter(c, row)
    path = f"/admin/comics/{row['id']}/chapters/{ch['id']}/pages"
    assert upload(c, path).status_code == 201
    assert upload(c, path, version=2).status_code == 201
    pages = c.get(path).json()["items"]
    with session_scope(db_engine) as db:
        db.get(Comic, uuid.UUID(row["id"])).status = "published"
    return c, row, ch, path, pages


def payload(pages, **kwargs):
    return {
        "page_id": pages[1]["id"],
        "offset_milli": 350,
        "mode": "vertical",
        "version": 0,
        "chapter_version": 3,
        **kwargs,
    }


def test_catalogue_private_images_and_live_revocation(readable, db_engine):
    c, row, ch, _, pages = readable
    base = f"/reader/chapters/{ch['id']}"
    img = base + f"/pages/{pages[0]['id']}/image"
    assert c.get("/comics?q=Truyện").json()["total"] == 1
    assert c.get("/comics?q=%").json()["total"] == 0
    assert c.get("/comics?page=1001").status_code == 422
    assert c.get("/comics/reader-story").json()["items"][0]["id"] == ch["id"]
    response = c.get(img)
    assert response.status_code == 200 and response.content.startswith(b"\xff\xd8")
    assert response.headers["cache-control"] == "no-store"
    assert "storage_key" not in c.get(base).text
    with session_scope(db_engine) as db:
        db.get(Comic, uuid.UUID(row["id"])).status = "draft"
    assert c.get("/comics").json()["total"] == 0
    for path in ["/comics/reader-story", base, img]:
        assert c.get(path).status_code == 404
    assert c.put(base + "/progress", json=payload(pages)).status_code == 404
    c.cookies.clear()
    assert c.get(img).status_code == 401


def test_bookmark_stable_reorder_deleted_page_and_stale_chapter(readable):
    c, _, ch, path, pages = readable
    base = f"/reader/chapters/{ch['id']}"
    assert c.put(base + "/progress", json=payload(pages)).json()["version"] == 1
    assert (
        c.put(
            path + "/order", json={"version": 3, "page_ids": [p["id"] for p in reversed(pages)]}
        ).status_code
        == 200
    )
    saved = c.get(base).json()
    assert (
        saved["progress"]["page_id"] == pages[1]["id"] and saved["progress"]["offset_milli"] == 350
    )
    assert saved["pages"][0]["id"] == pages[1]["id"]
    assert c.put(base + "/progress", json=payload(pages, version=1)).status_code == 409
    assert (
        c.put(
            base + "/progress", json=payload(pages, version=1, chapter_version=4, mode="paged")
        ).status_code
        == 200
    )
    assert c.delete(path + f"/{pages[1]['id']}?version=4").status_code == 204
    saved = c.get(base).json()["progress"]
    assert saved == {"page_id": pages[0]["id"], "offset_milli": 0, "mode": "paged", "version": 2}
    assert (
        c.put(base + "/progress", json=payload(pages, version=2, chapter_version=5)).status_code
        == 422
    )


def test_progress_isolation_bounds_idor_csrf_and_concurrent_writer(readable, db_engine):
    c, row, ch, _, pages = readable
    base = f"/reader/chapters/{ch['id']}"
    with ThreadPoolExecutor(2) as pool:
        responses = list(
            pool.map(lambda _: c.put(base + "/progress", json=payload(pages)), range(2))
        )
    assert sorted(r.status_code for r in responses) == [200, 409]
    other = chapter(c, row, 2)
    other_base = f"/reader/chapters/{other['id']}"
    assert c.get(other_base + f"/pages/{pages[1]['id']}/image").status_code == 404
    assert (
        c.put(other_base + "/progress", json=payload(pages, chapter_version=1)).status_code == 422
    )
    password = "Reader password test 123!"
    c.post(
        "/auth/register",
        json={"email": "reader@example.com", "display_name": "Reader", "password": password},
    )
    assert (
        c.post(
            "/auth/login", json={"email": "reader@example.com", "password": password}
        ).status_code
        == 200
    )
    assert c.get(base).json()["progress"]["version"] == 0
    assert c.put(base + "/progress", json=payload(pages)).status_code == 200
    with session_scope(db_engine) as db:
        assert len(list(db.scalars(select(ReadingProgress)))) == 2
    assert (
        c.put(base + "/progress", json=payload(pages, version=1, offset_milli=1001)).status_code
        == 422
    )
    assert (
        c.put(
            base + "/progress", json=payload(pages, version=1, user_id=str(uuid.uuid4()))
        ).status_code
        == 422
    )
    c.headers.pop("X-CSRF-Token")
    assert c.put(base + "/progress", json=payload(pages)).status_code == 403
    assert c.put(base + "/progress", content=b"x" * 8193).status_code == 413


def test_reader_paid_plan_disabled_user_and_logout(readable, db_engine):
    c, row, ch, _, pages = readable
    base = f"/reader/chapters/{ch['id']}"
    img = base + f"/pages/{pages[0]['id']}/image"
    with session_scope(db_engine) as db:
        db.execute(update(User).values(role="user", plan_code="premium"))
        db.get(Comic, uuid.UUID(row["id"])).required_plan_code = "vip"
    assert c.get(base).status_code == 403 and c.get(img).status_code == 403
    assert c.put(base + "/progress", json=payload(pages)).status_code == 403
    with session_scope(db_engine) as db:
        db.get(Comic, uuid.UUID(row["id"])).required_plan_code = "free"
    assert c.get(img).status_code == 200
    assert c.post("/auth/logout").status_code == 204
    assert c.get(img).status_code == 401
    assert (
        c.post(
            "/auth/login",
            json={"email": "admin@example.com", "password": "Test admin password 123!"},
        ).status_code
        == 200
    )
    with session_scope(db_engine) as db:
        db.execute(update(User).values(is_active=False))
    assert c.get(img).status_code == 401


def test_stage09_rollback_preserves_comic(db_engine):
    with session_scope(db_engine) as db:
        row = Comic(title="Preserve Reader", slug="preserve-09")
        db.add(row)
        db.flush()
        identifier = row.id
    config = Config("alembic.ini")
    command.downgrade(config, "0007_comic_admin")
    migrate_and_seed()
    command.check(config)
    with session_scope(db_engine) as db:
        assert db.get(Comic, identifier).title == "Preserve Reader"
        db.execute(delete(Comic).where(Comic.id == identifier))
