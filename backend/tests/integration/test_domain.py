import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, inspect, select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app.config import Settings, get_settings
from app.database import make_engine, session_scope
from app.migrate import migrate_and_seed
from app.models import Chapter, Comic, ComicPage, Episode, Movie, Plan, User
from app.seed import seed_plans

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION") != "1",
        reason="Requires isolated Docker stack",
    ),
]


def user(**overrides):
    # Deliberately non-authenticating test fixture; never used by seed or app defaults.
    return User(
        email=f"{uuid.uuid4()}@example.test",
        display_name="Người đọc",
        password_hash="$argon2id$test-only-not-a-real-hash",
        **overrides,
    )


def test_seed_twice_keeps_exactly_three_plans_without_accounts(db):
    seed_plans(db)
    seed_plans(db)
    assert db.scalar(select(func.count()).select_from(Plan)) == 3
    assert db.scalar(select(func.count()).select_from(User)) == 0
    vip = db.get(Plan, "vip")
    premium = db.get(Plan, "premium")
    assert vip.price_vnd is premium.price_vnd is None
    assert not vip.is_active and not premium.is_available_for_purchase


def test_reseed_preserves_operator_configuration(db):
    vip = db.get(Plan, "vip")
    vip.price_vnd = 99000  # test value only, not a product price
    vip.duration_days = 30
    vip.device_limit = 2
    vip.is_active = True
    vip.is_available_for_purchase = True
    db.flush()
    seed_plans(db)
    db.expire_all()
    assert db.get(Plan, "vip").price_vnd == 99000
    assert db.get(Plan, "vip").is_available_for_purchase


def test_concurrent_seeding_is_idempotent(db_engine):
    with session_scope(db_engine) as session:
        session.execute(delete(Plan).where(Plan.code.in_(("vip", "premium"))))

    def run():
        with session_scope(db_engine) as session:
            seed_plans(session)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: run(), range(8)))
    with session_scope(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(Plan)) == 3


def test_user_defaults_and_restrict_plan_deletion(db):
    account = user()
    db.add(account)
    db.flush()
    assert account.role == "user" and account.plan_code == "free" and account.is_active
    assert account.created_at.tzinfo is not None
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(delete(Plan).where(Plan.code == "free"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("email", "Upper@Example.test"),
        ("email", " x@example.test"),
        ("email", "invalid"),
        ("role", "superadmin"),
        ("password_hash", "plaintext-secret"),
        ("display_name", "  "),
        ("plan_code", "unknown"),
    ],
)
def test_user_constraints(db, field, value):
    account = user()
    setattr(account, field, value)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(account)
        db.flush()


def test_duplicate_email_rejected(db):
    first, second = user(), user()
    second.email = first.email
    db.add(first)
    db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(second)
        db.flush()


@pytest.mark.parametrize(
    "values",
    [
        {"price_vnd": -1},
        {"duration_days": 0},
        {"device_limit": 0},
        {"is_available_for_purchase": True},
        {
            "is_active": True,
            "price_vnd": 0,
            "duration_days": 30,
            "device_limit": 1,
            "is_available_for_purchase": True,
        },
    ],
)
def test_plan_constraints_reject_invalid_or_unpriced_purchase(db, values):
    with pytest.raises(IntegrityError), db.begin_nested():
        for key, value in values.items():
            setattr(db.get(Plan, "vip"), key, value)
        db.flush()


@pytest.mark.parametrize(
    "values",
    [
        {"title": " "},
        {"slug": "../bad"},
        {"status": "secret"},
        {"required_plan_code": "unknown"},
        {"release_year": 1000},
    ],
)
def test_movie_constraints(db, values):
    attributes = {"title": "Phim kiểm thử", "slug": "test-movie"} | values
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(Movie(**attributes))
        db.flush()


def test_movie_episode_uniqueness_fk_and_cascade(db):
    movie = Movie(title="Phim kiểm thử", slug="test-movie")
    movie.episodes.append(Episode(title="Tập 1", episode_number=1))
    db.add(movie)
    db.flush()
    assert movie.status == "draft" and movie.required_plan_code == "free"
    for episode in (
        Episode(movie_id=movie.id, title="Trùng", episode_number=1),
        Episode(movie_id=uuid.uuid4(), title="Mồ côi", episode_number=1),
        Episode(movie_id=movie.id, title="Âm", episode_number=0),
        Episode(movie_id=movie.id, title="Duration", episode_number=2, duration_seconds=-1),
    ):
        with pytest.raises(IntegrityError), db.begin_nested():
            db.add(episode)
            db.flush()
    db.execute(delete(Movie).where(Movie.id == movie.id))
    assert db.scalar(select(func.count()).select_from(Episode)) == 0


def test_comic_relationships_reorder_and_cascade(db):
    comic = Comic(title="Truyện kiểm thử", slug="test-comic")
    chapter = Chapter(chapter_number=1, title="Chương 1")
    chapter.pages = [
        ComicPage(page_number=i, storage_key=f"comics/test/{i}.webp", width=800, height=1200)
        for i in (1, 2)
    ]
    comic.chapters.append(chapter)
    db.add(comic)
    db.flush()
    assert comic.status == "draft"
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(Chapter(comic_id=comic.id, chapter_number=1, title="Trùng"))
        db.flush()
    first, second = chapter.pages
    db.execute(text("SET CONSTRAINTS uq_comic_pages_position DEFERRED"))
    first.page_number, second.page_number = second.page_number, first.page_number
    db.flush()
    db.execute(text("SET CONSTRAINTS uq_comic_pages_position IMMEDIATE"))
    db.expire(chapter, ["pages"])
    assert [page.id for page in chapter.pages] == [second.id, first.id]
    db.execute(delete(Comic).where(Comic.id == comic.id))
    assert db.scalar(select(func.count()).select_from(Chapter)) == 0
    assert db.scalar(select(func.count()).select_from(ComicPage)) == 0


@pytest.mark.parametrize(
    "storage_key",
    [
        "../escape.png",
        "/absolute.png",
        "https://evil.test/a.png",
        "x.svg",
        "a//b.png",
        "a/../../b.png",
        "a\\b.png",
        "a%2fb.png",
    ],
)
def test_comic_pages_reject_unsafe_storage_keys(db, storage_key):
    comic = Comic(title="Test", slug="comic")
    chapter = Chapter(title="Test", chapter_number=1, comic=comic)
    db.add(chapter)
    db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            ComicPage(
                chapter_id=chapter.id, page_number=1, storage_key=storage_key, width=1, height=1
            )
        )
        db.flush()


def test_timestamp_trigger_covers_raw_sql_and_preserves_created_at(db):
    movie = Movie(title="Before", slug="time-test")
    db.add(movie)
    db.flush()
    created_at = movie.created_at
    before = movie.updated_at
    db.execute(
        text("UPDATE movies SET title='After', created_at='2000-01-01' WHERE id=:id"),
        {"id": movie.id},
    )
    db.refresh(movie)
    assert movie.created_at == created_at
    assert movie.updated_at >= before


def test_page_constraints_and_duplicate_position(db):
    comic = Comic(title="Test", slug="page-test")
    chapter = Chapter(title="Test", chapter_number=1, comic=comic)
    db.add(chapter)
    db.flush()
    db.add(
        ComicPage(
            chapter_id=chapter.id,
            page_number=1,
            storage_key="pages/one.png",
            width=800,
            height=1200,
        )
    )
    db.flush()
    for changes in (
        {"page_number": 1},
        {"page_number": 0},
        {"width": 0},
        {"height": -1},
        {"chapter_id": uuid.uuid4()},
        {"storage_key": "pages/one.png"},
    ):
        attributes = {
            "chapter_id": chapter.id,
            "page_number": 2,
            "storage_key": "pages/two.png",
            "width": 800,
            "height": 1200,
        } | changes
        with pytest.raises(IntegrityError), db.begin_nested():
            db.add(ComicPage(**attributes))
            db.flush()


def test_database_logs_omit_row_details_and_sql(db):
    assert db.scalar(text("SHOW log_error_verbosity")) == "terse"
    assert db.scalar(text("SHOW log_min_error_statement")) == "panic"
    assert db.scalar(text("SHOW log_parameter_max_length_on_error")) == "0"
    assert db.scalar(text("SHOW log_statement")) == "none"


def test_failed_transaction_rolls_back_all_writes(db_engine):
    slug = f"rollback-{uuid.uuid4()}"
    with pytest.raises(IntegrityError), session_scope(db_engine) as session:
        session.add(Movie(title="Rollback", slug=slug))
        session.flush()
        session.add(Episode(movie_id=uuid.uuid4(), title="Invalid FK", episode_number=1))
        session.flush()
    with session_scope(db_engine) as session:
        assert session.scalar(select(Movie).where(Movie.slug == slug)) is None


def runtime_engine():
    settings = Settings(
        _env_file=None,
        **(
            get_settings().model_dump()
            | {
                "database_url": os.environ["RUNTIME_DATABASE_URL"],
            }
        ),
    )
    return make_engine(settings)


def test_runtime_has_only_current_stage_read_permissions(db_engine):
    engine = runtime_engine()
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_user")) == "suni_runtime"
            assert connection.scalar(text("SELECT count(*) FROM plans")) == 3
            flags = connection.execute(
                text(
                    "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
                    "FROM pg_roles WHERE rolname=current_user",
                )
            ).one()
            assert not any(flags)
        for query in (
            "CREATE TABLE forbidden (id int)",
            "CREATE TEMP TABLE forbidden (id int)",
            "ALTER TABLE plans ADD COLUMN forbidden int",
            "DROP TABLE movies",
            "UPDATE plans SET price_vnd=1 WHERE code='vip'",
            "DELETE FROM audit_events",
            "UPDATE audit_events SET action='delete'",
            "UPDATE users SET role='admin'",
            "UPDATE users SET plan_code='premium'",
            "DELETE FROM users",
            "DELETE FROM payment_orders",
            "DELETE FROM payment_events",
            "UPDATE subscriptions SET device_limit=20",
            "INSERT INTO users (email, display_name, password_hash, role) "
            "VALUES ('x@example.com', 'X', '$argon2id$test', 'admin')",
            "SELECT * FROM alembic_version",
            "SET ROLE suni_migrator",
        ):
            with engine.connect() as connection, pytest.raises(ProgrammingError):
                connection.execute(text(query))
    finally:
        engine.dispose()


def test_migrator_is_not_superuser(db_engine):
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT current_user")) == "suni_migrator"
        assert not connection.scalar(
            text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")
        )


def test_stage02_rollback_reapply_drift_and_seed(db_engine):
    config = Config("alembic.ini")
    command.downgrade(config, "0001_bootstrap")
    assert inspect(db_engine).get_table_names() == ["alembic_version"]
    migrate_and_seed()
    command.check(config)
    assert set(inspect(db_engine).get_table_names()) == {
        "alembic_version",
        "plans",
        "users",
        "movies",
        "episodes",
        "comics",
        "chapters",
        "comic_pages",
        "comic_page_assets",
        "reading_progress",
        "content_grants",
        "content_devices",
        "payment_orders",
        "payment_events",
        "subscriptions",
        "auth_sessions",
        "refresh_tokens",
        "genres",
        "movie_genres",
        "audit_events",
        "upload_sessions",
        "upload_chunks",
        "media_jobs",
        "media_variants",
        "subtitle_tracks",
        "watch_progress",
    }
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM plans")) == 3
        assert connection.scalar(text("SELECT count(*) FROM users")) == 0
