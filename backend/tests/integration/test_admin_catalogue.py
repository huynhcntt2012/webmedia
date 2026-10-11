import os
import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text, update

from app.config import Settings, get_settings
from app.database import session_scope
from app.main import create_app
from app.migrate import migrate_and_seed
from app.models import AuditEvent, Episode, Genre, Movie, User

pytestmark = pytest.mark.integration
PASSWORD = "Test admin password 123!"


@pytest.fixture
def admin_api(db_engine):
    settings = Settings(
        _env_file=None,
        **(
            get_settings().model_dump()
            | {
                "database_url": os.environ["RUNTIME_DATABASE_URL"],
                "app_secret": secrets.token_hex(32),
                "auth_ip_limit": 5000,
                "auth_account_limit": 5000,
                "poster_allowed_hosts": "media.sunifactory.com",
            }
        ),
    )
    app = create_app(settings)
    with TestClient(app) as client:
        client.headers["Origin"] = settings.public_origin
        client.headers["X-CSRF-Token"] = client.get("/auth/csrf").json()["csrf_token"]
        client.post(
            "/auth/register",
            json={"email": "admin@example.com", "display_name": "Admin", "password": PASSWORD},
        )
        with session_scope(db_engine) as db:
            db.execute(update(User).where(User.email == "admin@example.com").values(role="admin"))
        assert (
            client.post(
                "/auth/login", json={"email": "admin@example.com", "password": PASSWORD}
            ).status_code
            == 200
        )
        yield client
    with session_scope(db_engine) as db:
        db.execute(delete(Movie))
        db.execute(delete(Genre))
        db.execute(delete(AuditEvent))
        db.execute(delete(User))


def film(client, **values):
    response = client.post(
        "/admin/movies", json={"title": "Test movie", "slug": "test-movie", **values}
    )
    assert response.status_code == 201, response.text
    return response.json()


def edit_payload(row, **values):
    return (
        {k: v for k, v in row.items() if k not in {"id", "genres"}}
        | {"genre_ids": [g["id"] for g in row["genres"]]}
        | values
    )


def test_crud_publication_and_atomic_audit(admin_api, db_engine):
    g = admin_api.post("/admin/genres", json={"name": "Phiêu lưu", "slug": "phieu-luu"}).json()
    row = film(
        admin_api,
        genre_ids=[g["id"]],
        poster_url="https://media.sunifactory.com/posters/test.webp",
        trailer_url="https://youtu.be/abcdefghijk",
    )
    path = "/admin/movies/" + row["id"]
    assert admin_api.get("/movies/test-movie").status_code == 404
    assert admin_api.get(path).json()["genres"][0]["name"] == "Phiêu lưu"
    saved = admin_api.put(path, json=edit_payload(row, status="published")).json()
    assert saved["version"] == 2
    public = admin_api.get("/movies/test-movie").json()
    assert public["genres"] == ["Phiêu lưu"] and public["poster_url"].endswith(".webp")
    assert public["trailer_url"] == "https://www.youtube.com/watch?v=abcdefghijk"
    assert admin_api.delete("/admin/genres/" + g["id"] + "?version=1").status_code == 409
    assert admin_api.put(path, json=edit_payload(row, title="Stale")).status_code == 409
    assert admin_api.delete(path + "?version=1").status_code == 409
    assert (
        admin_api.post(path + "/episodes", json={"title": "Pilot", "episode_number": 1}).status_code
        == 201
    )
    assert admin_api.delete(path + "?version=2").status_code == 204
    assert admin_api.get("/movies/test-movie").status_code == 404
    assert admin_api.delete("/admin/genres/" + g["id"] + "?version=1").status_code == 204
    with session_scope(db_engine) as db:
        assert not list(db.scalars(select(Episode)))
        events = list(db.scalars(select(AuditEvent)))
        assert len(events) == 6 and all(event.actor_id for event in events)
    assert admin_api.get("/admin/audit-events").json()["total"] == 6


def test_conflict_rolls_back_audit(admin_api):
    film(admin_api)
    before = admin_api.get("/admin/audit-events").json()["total"]
    assert (
        admin_api.post(
            "/admin/movies", json={"title": "Duplicate", "slug": "test-movie"}
        ).status_code
        == 409
    )
    assert admin_api.get("/admin/audit-events").json()["total"] == before
    assert (
        admin_api.post(
            "/admin/movies",
            json={"title": "Bad genre", "slug": "bad-genre", "genre_ids": [str(uuid.uuid4())]},
        ).status_code
        == 422
    )


def test_genre_edit_and_conflicts(admin_api):
    row = admin_api.post("/admin/genres", json={"name": "Drama", "slug": "drama"}).json()
    path = "/admin/genres/" + row["id"]
    assert (
        admin_api.put(path, json={"name": "Kịch", "slug": "kich", "version": 1}).json()["version"]
        == 2
    )
    assert admin_api.put(path, json={"name": "Old", "slug": "old", "version": 1}).status_code == 409
    assert (
        admin_api.post("/admin/genres", json={"name": "Kịch", "slug": "another"}).status_code == 409
    )
    assert admin_api.delete(path + "?version=2").status_code == 204


def test_episode_ownership_version_and_position(admin_api):
    a, b = film(admin_api), film(admin_api, slug="other")
    path = "/admin/movies/" + a["id"] + "/episodes"
    episode = admin_api.post(path, json={"title": "Pilot", "episode_number": 1}).json()
    assert admin_api.post(path, json={"title": "Duplicate", "episode_number": 1}).status_code == 409
    payload = {"title": "Updated", "episode_number": 2, "version": 1}
    assert (
        admin_api.put(
            "/admin/movies/" + b["id"] + "/episodes/" + episode["id"], json=payload
        ).status_code
        == 404
    )
    assert admin_api.put(path + "/" + episode["id"], json=payload).json()["version"] == 2
    assert admin_api.delete(path + "/" + episode["id"] + "?version=1").status_code == 409
    assert admin_api.get(path).json()["items"][0]["episode_number"] == 2
    assert admin_api.delete(path + "/" + episode["id"] + "?version=2").status_code == 204


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/admin/movies"),
        ("GET", "/admin/genres"),
        ("GET", "/admin/audit-events"),
        ("GET", "/admin/catalogue-settings"),
        ("POST", "/admin/movies"),
        ("POST", "/admin/genres"),
        ("PUT", "/admin/movies/00000000-0000-0000-0000-000000000001"),
        ("DELETE", "/admin/movies/00000000-0000-0000-0000-000000000001?version=1"),
        ("POST", "/admin/movies/00000000-0000-0000-0000-000000000001/episodes"),
        ("PUT", "/admin/genres/00000000-0000-0000-0000-000000000001"),
        ("DELETE", "/admin/genres/00000000-0000-0000-0000-000000000001?version=1"),
        ("GET", "/admin/movies/00000000-0000-0000-0000-000000000001/episodes"),
        (
            "PUT",
            "/admin/movies/00000000-0000-0000-0000-000000000001/episodes/00000000-0000-0000-0000-000000000002",
        ),
        (
            "DELETE",
            "/admin/movies/00000000-0000-0000-0000-000000000001/episodes/00000000-0000-0000-0000-000000000002?version=1",
        ),
    ],
)
def test_every_route_requires_admin(admin_api, db_engine, method, path):
    with session_scope(db_engine) as db:
        db.execute(update(User).where(User.email == "admin@example.com").values(role="user"))
    assert admin_api.request(method, path, json={}).status_code == 403
    admin_api.cookies.clear()
    assert admin_api.request(method, path, json={}).status_code == 401


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_admin_csrf_all_writes(admin_api, method):
    row = film(admin_api)
    admin_api.headers.pop("X-CSRF-Token")
    path = "/admin/movies" + ("" if method == "POST" else "/" + row["id"] + "?version=1")
    assert admin_api.request(method, path, json=edit_payload(row)).status_code == 403


def test_admin_validation_bounds_and_url_allowlist(admin_api):
    for values in (
        {"poster_url": "http://127.0.0.1/a.jpg"},
        {"poster_url": "https://evil.com/a.png"},
        {"trailer_url": "https://evil.com/watch"},
        {"role": "admin"},
        {"genre_ids": [str(uuid.uuid4())] * 2},
    ):
        assert (
            admin_api.post(
                "/admin/movies", json={"title": "Movie", "slug": "movie", **values}
            ).status_code
            == 422
        )
    assert admin_api.get("/admin/movies?page=1001").status_code == 422
    assert admin_api.get("/admin/movies?status=unknown").status_code == 422
    assert admin_api.get("/admin/movies/not-a-uuid").status_code == 422
    assert admin_api.post("/admin/movies", content=b"x" * 32769).status_code == 413


def test_two_edits_one_winner(admin_api):
    row = film(admin_api)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda name: (
                    admin_api.put(
                        "/admin/movies/" + row["id"], json=edit_payload(row, title=name)
                    ).status_code
                ),
                ["A", "B"],
            )
        )
    assert sorted(results) == [200, 409]
    assert admin_api.get("/admin/audit-events").json()["total"] == 2


def test_stage05_rollback_preserves_catalogue(db_engine):
    with session_scope(db_engine) as db:
        row = Movie(title="Preserved", slug="preserved")
        db.add(row)
        db.flush()
        identifier = row.id
    config = Config("alembic.ini")
    command.downgrade(config, "0003_auth")
    with db_engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT title FROM movies WHERE id=:id"), {"id": identifier})
            == "Preserved"
        )
    migrate_and_seed()
    command.check(config)
    with session_scope(db_engine) as db:
        assert db.get(Movie, identifier).version == 1
        db.execute(delete(Movie).where(Movie.id == identifier))
