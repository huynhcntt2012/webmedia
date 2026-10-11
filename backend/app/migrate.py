"""Upgrade, seed and grant explicit stage-specific privileges as suni_migrator."""

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.config import get_settings
from app.database import make_engine, session_scope
from app.seed import seed_plans

# Stage 03 adds authentication privileges without role/plan update or DDL rights.
# No future-table grants; each stage must test its explicit runtime permissions.
CATALOGUE_TABLES = ("plans", "movies", "episodes", "comics", "chapters", "comic_pages")


def grant_runtime_access(connection) -> None:
    connection.execute(text("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM suni_runtime"))
    connection.execute(text("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM suni_runtime"))
    for table in CATALOGUE_TABLES:
        connection.execute(text(f"GRANT SELECT ON TABLE {table} TO suni_runtime"))
    connection.execute(text("GRANT SELECT ON users TO suni_runtime"))
    connection.execute(
        text("GRANT INSERT (id, email, display_name, password_hash) ON users TO suni_runtime")
    )
    connection.execute(
        text("GRANT SELECT, INSERT ON auth_sessions, refresh_tokens TO suni_runtime")
    )
    connection.execute(text("GRANT UPDATE (revoked_at) ON auth_sessions TO suni_runtime"))
    connection.execute(text("GRANT UPDATE (consumed_at) ON refresh_tokens TO suni_runtime"))
    for table in ("movies", "episodes", "genres", "movie_genres"):
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO suni_runtime"))
    connection.execute(text("GRANT SELECT, INSERT ON audit_events TO suni_runtime"))
    for table in ("upload_sessions", "upload_chunks", "media_jobs", "media_variants"):
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO suni_runtime"))
    for table in (
        "subtitle_tracks",
        "watch_progress",
        "reading_progress",
        "content_grants",
        "content_devices",
    ):
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO suni_runtime"))
    connection.execute(
        text("GRANT SELECT, INSERT, UPDATE ON payment_orders, payment_events TO suni_runtime")
    )
    connection.execute(text("GRANT SELECT, INSERT ON subscriptions TO suni_runtime"))
    for table in ("comics", "chapters", "comic_pages", "comic_page_assets"):
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO suni_runtime"))


def migrate_and_seed() -> None:
    command.upgrade(Config("alembic.ini"), "head")
    engine = make_engine(get_settings())
    try:
        with session_scope(engine) as session:
            seed_plans(session)
            grant_runtime_access(session.connection())
    finally:
        engine.dispose()


if __name__ == "__main__":
    migrate_and_seed()
    print("Migration, baseline seed and runtime grants completed.")
