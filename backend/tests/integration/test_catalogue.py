import os
import unicodedata

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, update

from app.config import Settings, get_settings
from app.database import session_scope
from app.main import create_app
from app.models import Movie

pytestmark = pytest.mark.integration


@pytest.fixture
def catalogue(db_engine):
    settings = Settings(
        _env_file=None,
        **(
            get_settings().model_dump()
            | {
                "database_url": os.environ["RUNTIME_DATABASE_URL"],
            }
        ),
    )
    with session_scope(db_engine) as db:
        db.add_all(
            [
                Movie(
                    slug="duong-ve",
                    title="Đường Về Mùa Hè",
                    synopsis="<script>alert(1)</script>",
                    status="published",
                ),
                Movie(
                    slug="literal",
                    title="100%_ nguyên bản",
                    status="published",
                    required_plan_code="vip",
                ),
                Movie(
                    slug="decomposed",
                    title=unicodedata.normalize("NFD", "Ánh trăng"),
                    status="published",
                ),
                Movie(slug="draft-secret", title="Đường Về Bí Mật", status="draft"),
                Movie(slug="archived-secret", title="Đường Về Lưu Trữ", status="archived"),
            ]
        )
    try:
        with TestClient(create_app(settings)) as client:
            yield client
    finally:
        with session_scope(db_engine) as db:
            db.execute(delete(Movie))


def test_public_list_and_detail_whitelist(catalogue):
    response = catalogue.get("/movies")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["total"] == 3
    assert {x["slug"] for x in response.json()["items"]} == {"duong-ve", "literal", "decomposed"}
    detail = catalogue.get("/movies/duong-ve").json()
    assert set(detail) == {
        "slug",
        "title",
        "synopsis",
        "release_year",
        "required_plan_code",
        "poster_url",
        "trailer_url",
        "genres",
    }
    assert detail["synopsis"] == "<script>alert(1)</script>"
    assert catalogue.get("/movies/literal").json()["required_plan_code"] == "vip"


@pytest.mark.parametrize("slug", ["draft-secret", "archived-secret", "does-not-exist"])
def test_hidden_indistinguishable_from_missing(catalogue, slug):
    response = catalogue.get("/movies/" + slug)
    assert response.status_code == 404
    assert response.json() == {"detail": "Không tìm thấy phim."}


@pytest.mark.parametrize(
    "query,slugs",
    [
        ("đƯỜNG vỀ", ["duong-ve"]),
        (unicodedata.normalize("NFD", "Mùa Hè"), ["duong-ve"]),
        ("Ánh trăng", ["decomposed"]),
        ("%_", ["literal"]),
        ("' OR 1=1 --", []),
        ("absent", []),
    ],
)
def test_unicode_literal_search(catalogue, query, slugs):
    response = catalogue.get("/movies", params={"q": query})
    assert response.status_code == 200
    assert [x["slug"] for x in response.json()["items"]] == slugs


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page": 1001},
        {"page": "oops"},
        {"page_size": 0},
        {"page_size": 49},
        {"sort": "password_hash"},
        {"q": "x" * 101},
    ],
)
def test_invalid_queries(catalogue, params):
    response = catalogue.get("/movies", params=params)
    assert response.status_code == 422
    assert response.json() == {"detail": "Tham số yêu cầu không hợp lệ."}


def test_stable_pagination_and_no_stale_publication(catalogue, db_engine):
    pages = [
        catalogue.get("/movies", params={"page_size": 1, "page": p}).json() for p in range(1, 5)
    ]
    assert len({p["items"][0]["slug"] for p in pages[:3]}) == 3
    assert pages[3]["items"] == []
    assert catalogue.get("/movies", params={"page_size": 1}).json() == pages[0]
    ordered = catalogue.get("/movies", params={"sort": "title"}).json()["items"]
    assert ordered[0]["slug"] == "literal"
    with session_scope(db_engine) as db:
        db.execute(update(Movie).where(Movie.slug == "duong-ve").values(status="draft"))
    assert catalogue.get("/movies/duong-ve").status_code == 404
    assert catalogue.get("/movies", params={"q": "Đường"}).json()["total"] == 0


def test_empty_catalogue(catalogue, db_engine):
    with session_scope(db_engine) as db:
        db.execute(delete(Movie))
    assert catalogue.get("/movies").json() == {"items": [], "total": 0, "page": 1, "page_size": 24}
