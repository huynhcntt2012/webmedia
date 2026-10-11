from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql

from app.bootstrap_db import provision_roles
from app.seed import PLAN_SEED, seed_plans


def test_seed_is_fail_closed_and_contains_no_accounts():
    free, vip, premium = PLAN_SEED
    assert free["code"] == "free" and free["price_vnd"] == 0 and free["is_active"]
    assert {row["code"] for row in PLAN_SEED} == {"free", "vip", "premium"}
    for row in (vip, premium):
        assert row["price_vnd"] is None
        assert row["duration_days"] is None
        assert row["device_limit"] is None
        assert not row["is_active"] and not row["is_available_for_purchase"]


def test_seed_conflicts_do_not_overwrite_prices_or_commit_callers_transaction():
    session = MagicMock()
    seed_plans(session)
    statement = session.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (code) DO NOTHING" in sql
    assert "DO UPDATE" not in sql
    session.commit.assert_not_called()


def test_provisioning_rejects_weak_or_shared_passwords_before_connecting():
    import pytest

    for first, second in (("weak", "b" * 64), ("a" * 64, "a" * 64)):
        with pytest.raises(ValueError):
            provision_roles("not-a-connection", first, second)
