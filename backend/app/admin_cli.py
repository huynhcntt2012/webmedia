"""Explicit operator-only role promotion. No default admin credentials."""

import argparse

from sqlalchemy import select

from app.config import get_settings
from app.database import make_engine, session_scope
from app.models import User


def main():
    parser = argparse.ArgumentParser(
        description="Promote an existing user using the migrator role."
    )
    parser.add_argument("user_id", help="UUID obtained by the account owner from /auth/me")
    args = parser.parse_args()
    import uuid

    user_id = uuid.UUID(args.user_id)
    engine = make_engine(get_settings())
    try:
        with session_scope(engine) as db:
            user = db.scalar(select(User).where(User.id == user_id))
            if not user or not user.is_active:
                raise SystemExit("Active user not found; no changes made.")
            user.role = "admin"
        print("Admin role assigned to the requested user.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
