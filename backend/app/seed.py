"""Idempotent baseline plans. Never overwrites operator-edited commercial data."""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Plan

PLAN_SEED = (
    {
        "code": "free",
        "name": "Free",
        "price_vnd": 0,
        "duration_days": None,
        "device_limit": None,
        "is_active": True,
        "is_available_for_purchase": False,
    },
    {
        "code": "vip",
        "name": "VIP",
        "price_vnd": None,
        "duration_days": None,
        "device_limit": None,
        "is_active": False,
        "is_available_for_purchase": False,
    },
    {
        "code": "premium",
        "name": "Premium",
        "price_vnd": None,
        "duration_days": None,
        "device_limit": None,
        "is_active": False,
        "is_available_for_purchase": False,
    },
)


def seed_plans(session: Session) -> None:
    """Caller owns the transaction; one atomic statement handles concurrent seeds."""
    session.execute(
        insert(Plan).values(list(PLAN_SEED)).on_conflict_do_nothing(index_elements=["code"])
    )


def main() -> None:
    from app.config import get_settings
    from app.database import make_engine, session_scope

    engine = make_engine(get_settings())
    try:
        with session_scope(engine) as session:
            seed_plans(session)
        print("Baseline plans seeded; existing rows preserved.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
