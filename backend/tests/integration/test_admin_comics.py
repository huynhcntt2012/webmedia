import hashlib
import io
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic import command
from alembic.config import Config
from PIL import Image
from sqlalchemy import delete, func, select, update

from app.database import session_scope
from app.migrate import migrate_and_seed
from app.models import AuditEvent, Chapter, Comic, ComicPage, ComicPageAsset, User
from tests.integration.test_admin_catalogue import admin_api  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.fixture
def comics_api(admin_api, db_engine):  # noqa: F811
    yield admin_api
    with session_scope(db_engine) as db:
        db.execute(delete(Comic))


def image_bytes(color="red"):
    buffer = io.BytesIO()
    Image.new("RGB", (40, 60), color).save(buffer, format="PNG")
    return buffer.getvalue()


def comic(client, slug=None):
    response = client.post(
        "/admin/comics", json={"title": "Truyện kiểm thử", "slug": slug or uuid.uuid4().hex}
    )
    assert response.status_code == 201, response.text
    return response.json()


def chapter(client, row, number=1):
    response = client.post(
        f"/admin/comics/{row['id']}/chapters",
        json={"title": "Chương kiểm thử", "chapter_number": number},
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload(client, path, data=None, key=None, version=1):
    data = data if data is not None else image_bytes()
    return client.post(
        path + f"?upload_key={key or uuid.uuid4()}&version={version}",
        content=data,
        headers={
            "Content-Type": "application/octet-stream",
            "X-Chunk-SHA256": hashlib.sha256(data).hexdigest(),
        },
    )


def test_comic_chapter_crud_conflicts_audit_and_pagination(comics_api, db_engine):
    c = comics_api
    row = comic(c, "comic-a")
    path = f"/admin/comics/{row['id']}"
    assert (
        c.post("/admin/comics", json={"title": "Duplicate", "slug": "comic-a"}).status_code == 409
    )
    data = {k: v for k, v in row.items() if k != "id"}
    assert (
        c.put(path, json=data | {"title": "Truyện đã sửa", "status": "published"}).json()["version"]
        == 2
    )
    assert c.put(path, json=data).status_code == 409
    assert c.get("/admin/comics?q=Truyện").json()["total"] == 1
    assert c.get("/admin/comics?page=1001").status_code == 422
    ch = chapter(c, row)
    cp = path + f"/chapters/{ch['id']}"
    assert (
        c.post(path + "/chapters", json={"title": "Duplicate", "chapter_number": 1}).status_code
        == 409
    )
    assert (
        c.put(cp, json={"title": "Chương đã sửa", "chapter_number": 2, "version": 1}).json()[
            "version"
        ]
        == 2
    )
    assert c.delete(cp + "?version=1").status_code == 409
    for number in range(3, 23):
        chapter(c, row, number)
    assert len(c.get(path + "/chapters").json()["items"]) == 20
    assert len(c.get(path + "/chapters?page=2").json()["items"]) == 1
    assert c.delete(cp + "?version=2").status_code == 204
    assert c.delete(path + "?version=2").status_code == 204
    with session_scope(db_engine) as db:
        assert not db.scalar(select(func.count()).select_from(Chapter))
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.entity_type == "comic")
            )
            == 3
        )


def test_real_image_batch_partial_retry_reorder_and_cascade(comics_api, db_engine):
    c = comics_api
    row = comic(c)
    ch = chapter(c, row)
    path = f"/admin/comics/{row['id']}/chapters/{ch['id']}/pages"
    key = uuid.uuid4()
    first = upload(c, path, key=key)
    assert first.status_code == 201, first.text
    p1 = first.json()["page"]["id"]
    assert upload(c, path, key=key).json()["page"]["id"] == p1
    assert upload(c, path, data=image_bytes("blue"), key=key).status_code == 409
    assert upload(c, path, data=b"<svg/>", version=2).status_code == 422
    assert c.get(path).json()["chapter"]["version"] == 2
    second = upload(c, path, data=image_bytes("blue"), version=2)
    assert second.status_code == 201, second.text
    p2 = second.json()["page"]["id"]
    response = c.get(path + f"/{p1}/image")
    assert response.status_code == 200
    assert (
        response.headers["content-type"] == "image/jpeg"
        and response.headers["cache-control"] == "no-store"
    )
    with Image.open(io.BytesIO(response.content)) as image:
        assert image.size == (40, 60)
    assert c.put(path + "/order", json={"version": 3, "page_ids": [p1, p1]}).status_code == 422
    assert (
        c.put(path + "/order", json={"version": 3, "page_ids": [p1, str(uuid.uuid4())]}).status_code
        == 422
    )
    result = c.put(path + "/order", json={"version": 3, "page_ids": [p2, p1]})
    assert result.status_code == 200, result.text
    assert [p["id"] for p in result.json()["items"]] == [p2, p1]
    assert c.put(path + "/order", json={"version": 3, "page_ids": [p1, p2]}).status_code == 409
    assert c.delete(path + f"/{p2}?version=4").status_code == 204
    assert c.get(path).json()["items"][0]["page_number"] == 1
    assert c.get(path + f"/{p2}/image").status_code == 404
    with session_scope(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(ComicPageAsset)) == 1
    assert c.delete(f"/admin/comics/{row['id']}?version=1").status_code == 204
    with session_scope(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(ComicPageAsset)) == 0
        assert db.scalar(select(func.count()).select_from(ComicPage)) == 0


def test_image_races_are_atomic(comics_api, db_engine):
    c = comics_api
    row = comic(c)
    ch = chapter(c, row)
    path = f"/admin/comics/{row['id']}/chapters/{ch['id']}/pages"
    key = uuid.uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: upload(c, path, key=key), range(2)))
    assert [r.status_code for r in results] == [201, 201]
    assert results[0].json()["page"]["id"] == results[1].json()["page"]["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: upload(c, path, version=2), range(2)))
    assert sorted(r.status_code for r in results) == [201, 409]
    pages = c.get(path).json()["items"]
    ids = [p["id"] for p in pages]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda values: (
                    c.put(path + "/order", json={"version": 3, "page_ids": values}).status_code
                ),
                [ids, list(reversed(ids))],
            )
        )
    assert sorted(results) == [200, 409]
    with session_scope(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(ComicPageAsset)) == 2


def test_comic_security_csrf_parent_scope_and_limits(comics_api, db_engine):
    c = comics_api
    row = comic(c)
    other = comic(c)
    ch = chapter(c, row)
    path = f"/admin/comics/{row['id']}/chapters/{ch['id']}/pages"
    assert c.get(f"/admin/comics/{other['id']}/chapters/{ch['id']}/pages").status_code == 404
    assert upload(c, path, data=b"x" * (8 * 1024 * 1024 + 1)).status_code == 413
    bad = c.post(
        path + f"?upload_key={uuid.uuid4()}&version=1",
        content=image_bytes(),
        headers={"Content-Type": "application/octet-stream", "X-Chunk-SHA256": "0" * 64},
    )
    assert bad.status_code == 422
    c.headers.pop("X-CSRF-Token")
    assert upload(c, path).status_code == 403
    with session_scope(db_engine) as db:
        db.execute(update(User).values(role="user"))
    assert c.get("/admin/comics").status_code == 403
    assert c.get(path + "/00000000-0000-0000-0000-000000000001/image").status_code == 403
    c.cookies.clear()
    assert c.get("/admin/comics").status_code == 401


def test_real_image_quota(comics_api):
    c = comics_api
    row = comic(c)
    ch = chapter(c, row)
    path = f"/admin/comics/{row['id']}/chapters/{ch['id']}/pages"
    c.app.state.settings.comic_quota_bytes = 1048576
    buffer = io.BytesIO()
    Image.effect_noise((1200, 1200), 100).convert("RGB").save(buffer, format="PNG")
    first = upload(c, path, data=buffer.getvalue())
    assert first.status_code == 201, first.text
    second = upload(c, path, data=buffer.getvalue(), version=2)
    assert second.status_code == 507, second.text
    assert len(c.get(path).json()["items"]) == 1


def test_stage08_rollback_preserves_comic(db_engine):
    with session_scope(db_engine) as db:
        row = Comic(title="Preserve", slug="preserve-08")
        db.add(row)
        db.flush()
        identifier = row.id
    config = Config("alembic.ini")
    command.downgrade(config, "0006_playback")
    migrate_and_seed()
    command.check(config)
    with session_scope(db_engine) as db:
        assert (
            db.get(Comic, identifier).title == "Preserve" and db.get(Comic, identifier).version == 1
        )
        db.execute(delete(Comic).where(Comic.id == identifier))
