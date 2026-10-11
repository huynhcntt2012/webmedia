"""Fictional fixtures ONLY for the isolated browser test database."""

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.config import get_settings
from app.database import make_engine, session_scope
from app.models import Movie, Plan, User
from app.security import passwords


def main():
    settings = get_settings()
    if (
        settings.app_env != "test"
        or make_url(settings.database_url.get_secret_value()).database != "suni_test"
    ):
        raise SystemExit("Refusing to seed outside isolated test database")
    engine = make_engine(settings)
    try:
        with session_scope(engine) as db:
            # Sample commercial values are confined to the guarded suni_test fixture.
            for code, price in [("vip", 50000), ("premium", 100000)]:
                plan = db.get(Plan, code)
                plan.price_vnd, plan.duration_days, plan.device_limit = price, 30, 2
                plan.is_active = plan.is_available_for_purchase = True
            if not db.scalar(select(User.id).where(User.email == "admin-browser@example.com")):
                db.add(
                    User(
                        email="admin-browser@example.com",
                        display_name="E2E Admin",
                        role="admin",
                        password_hash=passwords.hash("E2E-only-password-123!"),
                    )
                )
            if db.scalar(select(Movie.id).limit(1)):
                return
            for number in range(27):
                db.add(
                    Movie(
                        slug=f"test-story-{number:02}",
                        title=f"Câu chuyện kiểm thử {number:02}",
                        synopsis="Dữ liệu hư cấu chỉ dành cho kiểm thử trình duyệt.",
                        release_year=2026,
                        status="published",
                    )
                )
            db.add(
                Movie(
                    slug="test-vietnamese",
                    title="Đường Về Mùa Hè",
                    synopsis=(
                        "<script>window.catalogueXss = true</script>\nMột câu chuyện kiểm thử."
                    ),
                    status="published",
                    required_plan_code="premium",
                )
            )
            db.add(Movie(slug="test-draft", title="Bí mật chưa xuất bản", status="draft"))
            db.add(Movie(slug="test-archived", title="Phim đã lưu trữ", status="archived"))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
