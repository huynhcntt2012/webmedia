import hashlib
import subprocess
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, select, update

from app.config import get_settings
from app.database import session_scope
from app.media_storage import CHUNK_BYTES, upload_dir
from app.migrate import migrate_and_seed
from app.models import Episode, MediaJob, Movie, UploadSession, User
from app.transcode import run_media
from tests.integration.test_admin_catalogue import admin_api, film  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.fixture
def media_api(admin_api, db_engine):  # noqa: F811 - imported shared pytest fixture
    yield admin_api
    from app.media_tasks import media_maintenance

    with session_scope(db_engine) as db:
        db.execute(update(UploadSession).values(status="cancelled"))
    media_maintenance.delay().get(timeout=60)
    with session_scope(db_engine) as db:
        db.execute(delete(UploadSession))


def episode(client, number=1):
    movie = film(client, slug=f"media-{uuid.uuid4().hex}")
    response = client.post(
        f"/admin/movies/{movie['id']}/episodes",
        json={"title": "Video test", "episode_number": number},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def start(client, episode_id, size):
    response = client.post(
        "/admin/uploads",
        json={
            "episode_id": episode_id,
            "idempotency_key": str(uuid.uuid4()),
            "filename": "fixture.mp4",
            "total_bytes": size,
            "content_type": "video/mp4",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def chunk(client, identifier, data, offset=0, digest=None):
    return client.put(
        f"/admin/uploads/{identifier}/chunks?offset={offset}",
        content=data,
        headers={
            "Content-Type": "application/octet-stream",
            "X-Chunk-SHA256": digest or hashlib.sha256(data).hexdigest(),
        },
    )


def wait_job(client, identifier):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        row = client.get(f"/admin/uploads/{identifier}").json()
        if row["job"] and row["job"]["status"] in {"ready", "failed", "cancelled"}:
            return row["job"]
        time.sleep(0.3)
    pytest.fail("Real Celery job did not complete within 90 seconds")


@pytest.fixture
def video(tmp_path):
    path = tmp_path / "fixture.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1280x720:rate=24",
            "-t",
            "1",
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(path),
        ],
        check=True,
        timeout=30,
    )
    return path.read_bytes()


def test_real_ffmpeg_hls_thumbnail_outbox_and_duplicate(media_api, db_engine, video, monkeypatch):
    from app.media_tasks import media_maintenance, transcode_job

    client = media_api
    ep = episode(client)
    row = start(client, ep, len(video))
    identifier = row["id"]
    assert chunk(client, identifier, video).status_code == 200
    # Fault injection tests durable outbox only. Recovery below uses actual Redis/Celery.
    with monkeypatch.context() as patch:
        patch.setattr("app.uploads.enqueue", lambda _: False)
        completed = client.post(f"/admin/uploads/{identifier}/complete")
        assert completed.status_code == 202 and not completed.json()["dispatched"]
    assert media_maintenance.delay().get(timeout=60)["dispatched"] >= 1
    job = wait_job(client, identifier)
    assert job["status"] == "ready", job
    assert {v["height"] for v in job["variants"]} == {360, 720}
    assert client.post(f"/admin/uploads/{identifier}/complete").json()["job_id"] == job["id"]
    assert transcode_job.delay(job["id"]).get(timeout=60)["status"] == "ignored"
    directory = upload_dir(get_settings(), identifier)
    assert not (directory / "source.mp4").exists()
    output = directory / "output"
    assert "720p/index.m3u8" in (output / "master.m3u8").read_text()
    assert "#EXT-X-ENDLIST" in (output / "360p/index.m3u8").read_text()
    segment = next((output / "720p").glob("*.ts"))
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(segment), "-f", "null", "-"],
        check=True,
        timeout=30,
        stdout=subprocess.DEVNULL,
    )
    thumbnail = client.get(f"/admin/media-jobs/{job['id']}/thumbnail")
    assert thumbnail.status_code == 200 and thumbnail.content[:2] == b"\xff\xd8"
    assert thumbnail.headers["cache-control"] == "no-store"
    assert client.get(f"/media/{identifier}/output/master.m3u8").status_code == 404
    with session_scope(db_engine) as db:
        saved = db.get(UploadSession, uuid.UUID(identifier))
        assert saved.reserved_bytes < saved.total_bytes + 2147483648
        assert len(list(db.scalars(select(MediaJob).where(MediaJob.upload_id == saved.id)))) == 1
    with session_scope(db_engine) as db:
        movie_id = db.get(Episode, uuid.UUID(ep)).movie_id
    assert client.delete(f"/admin/movies/{movie_id}/episodes/{ep}?version=1").status_code == 204
    media_maintenance.delay().get(timeout=60)
    assert not directory.exists()


def test_resume_checksums_offsets_and_cancel(media_api):
    from app.media_tasks import media_maintenance

    client = media_api
    data = b"\x00\x00\x00\x18ftypisom" + b"0" * (CHUNK_BYTES - 12)
    row = start(client, episode(client), CHUNK_BYTES + 8)
    identifier = row["id"]
    assert chunk(client, identifier, data, digest="0" * 64).status_code == 422
    assert chunk(client, identifier, b"12345678", offset=CHUNK_BYTES).status_code == 409
    assert chunk(client, identifier, data).status_code == 200
    assert chunk(client, identifier, data).json()["received_bytes"] == CHUNK_BYTES
    assert chunk(client, identifier, data[:-1] + b"1").status_code == 409
    resumed = client.get(f"/admin/uploads/{identifier}").json()
    assert resumed["received_bytes"] == CHUNK_BYTES and len(resumed["chunks"]) == 1
    assert client.post(f"/admin/uploads/{identifier}/complete").status_code == 409
    assert chunk(client, identifier, b"12345678", offset=CHUNK_BYTES).status_code == 200
    assert client.delete(f"/admin/uploads/{identifier}").status_code == 202
    media_maintenance.delay().get(timeout=60)
    assert not upload_dir(get_settings(), identifier).exists()


def test_invalid_media_retries_are_bounded(media_api):
    data = b"\x00\x00\x00\x18ftypisom" + b"x" * 100
    row = start(media_api, episode(media_api), len(data))
    path = f"/admin/uploads/{row['id']}"
    assert chunk(media_api, row["id"], b"x" * len(data)).status_code == 415
    assert chunk(media_api, row["id"], data).status_code == 200
    assert media_api.post(path + "/complete").status_code == 202
    for attempt in range(1, 4):
        job = wait_job(media_api, row["id"])
        assert job["status"] == "failed" and job["attempts"] == attempt
        assert media_api.get(f"/admin/media-jobs/{job['id']}/thumbnail").status_code == 404
        assert media_api.post(path + "/retry").status_code == (202 if attempt < 3 else 409)


def test_expiry_auth_csrf_and_body_limit(media_api, db_engine):
    from app.media_tasks import media_maintenance

    row = start(media_api, episode(media_api), 12)
    path = f"/admin/uploads/{row['id']}"
    with session_scope(db_engine) as db:
        db.get(UploadSession, uuid.UUID(row["id"])).expires_at = datetime.now(UTC) - timedelta(
            seconds=1
        )
    assert chunk(media_api, row["id"], b"\x00\x00\x00\x18ftypisom").status_code == 409
    assert chunk(media_api, row["id"], b"x" * (CHUNK_BYTES + 1)).status_code == 413
    media_maintenance.delay().get(timeout=60)
    assert media_api.get(path).json()["status"] == "expired"
    media_api.headers.pop("X-CSRF-Token")
    assert media_api.delete(path).status_code == 403
    media_api.cookies.clear()
    assert media_api.get(path).status_code == 401


def test_decoder_network_denied():
    assert b"network-blocked" in run_media("network-test", [], capture=True)


def test_upload_ownership_and_quota(media_api, db_engine):
    client = media_api
    ep = episode(client)
    payload = {
        "episode_id": ep,
        "idempotency_key": str(uuid.uuid4()),
        "filename": "test.mp4",
        "total_bytes": 20,
        "content_type": "video/mp4",
    }
    first = client.post("/admin/uploads", json=payload)
    assert first.status_code == 201
    identifier = first.json()["id"]
    assert client.post("/admin/uploads", json=payload).json()["id"] == identifier
    assert client.post("/admin/uploads", json=payload | {"total_bytes": 21}).status_code == 409
    assert (
        client.post(
            "/admin/uploads", json=payload | {"idempotency_key": str(uuid.uuid4())}
        ).status_code
        == 409
    )
    settings = client.app.state.settings
    second_episode = episode(client)
    settings.upload_active_limit = 1
    second = payload | {"episode_id": second_episode, "idempotency_key": str(uuid.uuid4())}
    assert client.post("/admin/uploads", json=second).status_code == 429
    settings.upload_active_limit = 3
    settings.media_quota_bytes = 4294967296
    assert client.post("/admin/uploads", json=second).status_code == 507
    # Owner mismatch applies even to another administrator.
    password = "Test other administrator 123!"
    assert (
        client.post(
            "/auth/register",
            json={"email": "other@example.com", "display_name": "Other", "password": password},
        ).status_code
        == 202
    )
    with session_scope(db_engine) as db:
        db.execute(update(User).where(User.email == "other@example.com").values(role="admin"))
    assert (
        client.post(
            "/auth/login", json={"email": "other@example.com", "password": password}
        ).status_code
        == 200
    )
    assert client.get(f"/admin/uploads/{identifier}").status_code == 404
    assert client.delete(f"/admin/uploads/{identifier}").status_code == 404
    with session_scope(db_engine) as db:
        db.execute(update(User).where(User.email == "other@example.com").values(role="user"))
    assert client.get(f"/admin/uploads/{identifier}").status_code == 403


def test_stage06_migration_rollback(db_engine):
    with session_scope(db_engine) as db:
        row = Movie(title="Preserved", slug="stage06-preserved")
        db.add(row)
        db.flush()
        identifier = row.id
    config = Config("alembic.ini")
    command.downgrade(config, "0004_admin_catalogue")
    migrate_and_seed()
    command.check(config)
    with session_scope(db_engine) as db:
        assert db.get(Movie, identifier).title == "Preserved"
        db.execute(delete(Movie).where(Movie.id == identifier))
