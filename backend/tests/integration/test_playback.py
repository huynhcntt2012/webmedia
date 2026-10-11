import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, select, update

from app.database import session_scope
from app.migrate import migrate_and_seed
from app.models import Episode, Movie, User, WatchProgress
from tests.integration.test_admin_catalogue import admin_api  # noqa: F401
from tests.integration.test_media_pipeline import (  # noqa: F401
    chunk,
    episode,
    media_api,
    start,
    video,
    wait_job,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def playable(media_api, db_engine, video):  # noqa: F811
    ep = episode(media_api)
    upload = start(media_api, ep, len(video))
    assert chunk(media_api, upload["id"], video).status_code == 200
    assert media_api.post(f"/admin/uploads/{upload['id']}/complete").status_code == 202
    job = wait_job(media_api, upload["id"])
    assert job["status"] == "ready", job
    with session_scope(db_engine) as db:
        movie = db.get(Movie, db.get(Episode, uuid.UUID(ep)).movie_id)
        movie.status = "published"
        movie_id, slug = movie.id, movie.slug
    return media_api, ep, job["id"], movie_id, slug


def test_stream_range_subtitles_and_revocation(playable, db_engine):
    client, ep, job, movie_id, slug = playable
    base = f"/playback/jobs/{job}"
    assert client.get(f"/movies/{slug}/episodes").json()["items"][0]["ready"]
    assert client.get(f"/playback/episodes/{ep}").json()["job_id"] == job
    admin = f"/admin/media-jobs/{job}/subtitles/vi"
    data = {
        "label": "Tiếng Việt",
        "version": 0,
        "content": "WEBVTT\n\n00:00.000 --> 00:00.900\nXin chào & hello",
    }
    assert client.put(admin, json=data).status_code == 200
    assert client.put(admin, json=data).status_code == 409
    assert (
        client.put(
            admin, json=data | {"version": 1, "content": data["content"] + "<script>"}
        ).status_code
        == 422
    )
    assert "Xin chào &amp; hello" in client.get(base + "/subtitles/vi").text
    master = client.get(base + "/media/master.m3u8")
    assert master.status_code == 200 and master.headers["cache-control"] == "no-store"
    assert client.get(base + "/media/360p/index.m3u8").status_code == 200
    segment = base + "/media/360p/segment_00000.ts"
    ranged = client.get(segment, headers={"Range": "bytes=0-187"})
    assert ranged.status_code == 206 and len(ranged.content) == 188
    assert client.get(segment, headers={"Range": "bytes=0-1,4-5"}).status_code == 416
    for asset in ["source.mp4", "thumbnail.jpg", "360p/../../source.mp4", "9999p/index.m3u8"]:
        assert client.get(base + "/media/" + asset).status_code == 404
    with session_scope(db_engine) as db:
        db.get(Movie, movie_id).status = "draft"
    for suffix in [
        "/media/master.m3u8",
        "/media/360p/index.m3u8",
        "/media/360p/segment_00000.ts",
        "/subtitles/vi",
    ]:
        assert client.get(base + suffix).status_code == 404
    assert client.get(f"/movies/{slug}/episodes").status_code == 404
    with session_scope(db_engine) as db:
        db.get(Movie, movie_id).status = "published"
    assert client.delete(admin + "?version=1").status_code == 204
    assert client.get(base + "/subtitles/vi").status_code == 404
    assert client.post("/auth/logout").status_code == 204
    assert client.get(segment).status_code == 401


def test_progress_atomic_resume_completion_and_isolation(playable, db_engine):
    client, ep, job, _, _ = playable
    path = f"/playback/episodes/{ep}/progress"
    data = {"job_id": job, "position_ms": 400, "version": 0}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.put(path, json=data).status_code, range(2)))
    assert sorted(results) == [200, 409]
    assert client.get(f"/playback/episodes/{ep}").json()["progress"]["position_ms"] == 400
    assert client.get("/playback/continue").json()["items"][0]["episode_id"] == ep
    assert client.put(path, json=data | {"version": 1, "position_ms": 1001}).status_code == 422
    assert (
        client.put(path, json=data | {"version": 1, "user_id": str(uuid.uuid4())}).status_code
        == 422
    )
    assert client.put(path, json=data | {"version": 1, "position_ms": 1000}).json()["completed"]
    assert not client.get("/playback/continue").json()["items"]
    assert client.put(path, json=data | {"version": 2, "position_ms": 200}).status_code == 200
    assert client.put(path, json=data | {"version": 2, "position_ms": 300}).status_code == 409
    password = "Playback test password 123!"
    client.post(
        "/auth/register",
        json={"email": "viewer@example.com", "display_name": "Viewer", "password": password},
    )
    client.post("/auth/login", json={"email": "viewer@example.com", "password": password})
    assert client.get(f"/playback/episodes/{ep}").json()["progress"]["version"] == 0
    assert not client.get("/playback/continue").json()["items"]
    assert client.put(path, json=data).status_code == 200
    with session_scope(db_engine) as db:
        assert (
            len(
                list(
                    db.scalars(
                        select(WatchProgress).where(WatchProgress.episode_id == uuid.UUID(ep))
                    )
                )
            )
            == 2
        )
    client.headers.pop("X-CSRF-Token")
    assert client.put(path, json=data).status_code == 403
    assert client.put(path, content=b"x" * 8193).status_code == 413


def test_paid_fail_closed_even_draft_plan_and_disabled_account(playable, db_engine):
    client, ep, job, movie_id, _ = playable
    with session_scope(db_engine) as db:
        db.execute(update(User).values(role="user", plan_code="premium"))
        db.get(Movie, movie_id).required_plan_code = "vip"
    for path in [
        f"/playback/episodes/{ep}",
        f"/playback/jobs/{job}/media/master.m3u8",
        f"/playback/jobs/{job}/media/360p/segment_00000.ts",
        f"/playback/jobs/{job}/subtitles/vi",
    ]:
        assert client.get(path).status_code == 403
    with session_scope(db_engine) as db:
        db.get(Movie, movie_id).required_plan_code = "free"
    assert client.get(f"/playback/episodes/{ep}").status_code == 200
    with session_scope(db_engine) as db:
        db.execute(update(User).values(is_active=False))
    assert client.get(f"/playback/jobs/{job}/media/master.m3u8").status_code == 401


def test_video_replacement_resets_resume_and_invalidates_old_media(playable, video):  # noqa: F811
    client, ep, job, _, _ = playable
    path = f"/playback/episodes/{ep}"
    assert (
        client.put(
            path + "/progress", json={"job_id": job, "position_ms": 400, "version": 0}
        ).status_code
        == 200
    )
    upload = start(client, ep, len(video))
    assert chunk(client, upload["id"], video).status_code == 200
    client.post(f"/admin/uploads/{upload['id']}/complete")
    replacement = wait_job(client, upload["id"])
    assert replacement["status"] == "ready"
    assert client.get(path).json()["progress"] == {
        "position_ms": 0,
        "completed": False,
        "version": 1,
    }
    assert client.get(f"/playback/jobs/{job}/media/master.m3u8").status_code == 404
    assert not client.get("/playback/continue").json()["items"]
    assert (
        client.put(
            path + "/progress", json={"job_id": job, "position_ms": 400, "version": 1}
        ).status_code
        == 409
    )
    assert (
        client.put(
            path + "/progress", json={"job_id": replacement["id"], "position_ms": 200, "version": 1}
        ).status_code
        == 200
    )


def test_stage07_rollback_preserves_movies(db_engine):
    with session_scope(db_engine) as db:
        row = Movie(title="Preserved 07", slug="preserved-07")
        db.add(row)
        db.flush()
        identifier = row.id
    config = Config("alembic.ini")
    command.downgrade(config, "0005_media_uploads")
    migrate_and_seed()
    command.check(config)
    with session_scope(db_engine) as db:
        assert db.get(Movie, identifier).title == "Preserved 07"
        db.execute(delete(Movie).where(Movie.id == identifier))
