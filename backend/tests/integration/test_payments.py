import hashlib
import hmac
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, select, text

from app.config import Settings
from app.database import session_scope
from app.migrate import migrate_and_seed
from app.models import PaymentEvent, PaymentOrder, Plan, Subscription, User
from tests.integration.test_admin_catalogue import admin_api  # noqa: F401

pytestmark = pytest.mark.integration
SECRET = "local-test-webhook-secret-0123456789abcdef0123456789"


@pytest.fixture
def payments_api(admin_api, db_engine):  # noqa: F811
    c = admin_api
    c.app.state.settings = Settings(
        _env_file=None,
        **(
            c.app.state.settings.model_dump()
            | {
                "payment_mode": "sandbox",
                "sepay_webhook_secret": SECRET,
                "sepay_bank": "TestBank",
                "sepay_account": "TEST123456",
            }
        ),
    )
    with session_scope(db_engine) as db:
        for code, price in [("vip", 50000), ("premium", 100000)]:
            p = db.get(Plan, code)
            p.price_vnd, p.duration_days, p.device_limit = price, 30, 2
            p.is_active = p.is_available_for_purchase = True
    yield c
    with session_scope(db_engine) as db:
        db.execute(delete(Subscription))
        db.execute(delete(PaymentEvent))
        db.execute(delete(PaymentOrder))
        for code in ["vip", "premium"]:
            p = db.get(Plan, code)
            p.price_vnd = p.duration_days = p.device_limit = None
            p.is_active = p.is_available_for_purchase = False


def order(c, code="vip", key=None):
    response = c.post(
        "/payments/orders", json={"plan_code": code, "idempotency_key": str(key or uuid.uuid4())}
    )
    assert response.status_code == 201, response.text
    return response.json()


def event(row, **changes):
    return {
        "id": uuid.uuid4().int % (2**53),
        "gateway": "TestBank",
        "accountNumber": "TEST123456",
        "subAccount": "",
        "code": row["payment_code"],
        "content": row["payment_code"] + " chuyen tien",
        "transferType": "in",
        "transferAmount": row["amount_vnd"],
        "transactionDate": datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M:%S"),
        "referenceCode": "local-fixture",
        **changes,
    }


def deliver(c, payload, secret=SECRET, timestamp=None, raw=None):
    body = raw if raw is not None else json.dumps(payload).encode()
    ts = str(timestamp or int(time.time()))
    signature = (
        "sha256=" + hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    )
    return c.post(
        "/payments/sepay/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-SePay-Signature": signature,
            "X-SePay-Timestamp": ts,
        },
    )


def test_order_server_snapshot_idempotency_race_quota(payments_api, db_engine):
    c = payments_api
    key = uuid.uuid4()
    with ThreadPoolExecutor(2) as pool:
        rows = list(pool.map(lambda _: order(c, key=key), range(2)))
    assert rows[0]["id"] == rows[1]["id"]
    with session_scope(db_engine) as db:
        db.get(Plan, "vip").price_vnd = 60000
    assert order(c, key=key)["amount_vnd"] == 50000
    assert (
        c.post(
            "/payments/orders", json={"plan_code": "premium", "idempotency_key": str(key)}
        ).status_code
        == 409
    )
    assert (
        c.post(
            "/payments/orders",
            json={"plan_code": "vip", "idempotency_key": str(uuid.uuid4()), "amount_vnd": 1},
        ).status_code
        == 422
    )
    for _ in range(4):
        order(c)
    assert (
        c.post(
            "/payments/orders", json={"plan_code": "vip", "idempotency_key": str(uuid.uuid4())}
        ).status_code
        == 429
    )
    assert c.get("/payments/orders").json()["total"] == 5


def test_webhook_authentication_before_write(payments_api, db_engine):
    c = payments_api
    row = order(c)
    payload = event(row)
    for kwargs in [
        {"secret": "bad"},
        {"timestamp": int(time.time()) - 301},
        {"timestamp": int(time.time()) + 301},
    ]:
        assert deliver(c, payload, **kwargs).status_code == 401
    assert deliver(c, payload, raw=b"x" * 16385).status_code == 413
    assert deliver(c, payload, raw=b'{"id":1,"id":2}').status_code == 422
    assert deliver(c, payload | {"currency": "USD"}).status_code == 422
    with session_scope(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(PaymentEvent)) == 0
    assert c.get(f"/payments/orders/{row['id']}").json()["status"] == "pending"


def test_concurrent_duplicates_grant_once_and_replay_conflict(payments_api, db_engine):
    c = payments_api
    row = order(c)
    payload = event(row)
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda _: deliver(c, payload), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert all(r.json() == {"success": True} for r in responses)
    assert deliver(c, payload).status_code == 200
    assert deliver(c, payload | {"transferAmount": 1}).status_code == 409
    assert deliver(c, event(row)).status_code == 200
    with session_scope(db_engine) as db:
        assert db.scalar(select(func.count()).select_from(Subscription)) == 1
        assert db.scalar(select(func.count()).select_from(PaymentEvent)) == 2
        assert db.scalar(select(User.plan_code)) == "free"
    assert c.get(f"/payments/orders/{row['id']}").json()["status"] == "paid"
    assert c.get("/payments/subscriptions").json()["items"][0]["environment"] == "sandbox"
    assert c.get("/admin/payment-events").json()["items"][0]["reason"] == "extra_payment"


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"gateway": "OtherBank"}, "wrong_receiver"),
        ({"accountNumber": "OTHER"}, "wrong_receiver"),
        ({"subAccount": "OTHER"}, "wrong_receiver"),
        ({"transferAmount": 1}, "wrong_amount_currency"),
        ({"transferAmount": 50001}, "wrong_amount_currency"),
        ({"transferType": "out"}, "outgoing"),
        ({"code": None}, "unknown_order"),
        ({"content": "not the code"}, "ambiguous_code"),
        ({"transactionDate": "2020-01-01 10:00:00"}, "outside_order_window"),
    ],
)
def test_mismatched_event_never_grants(payments_api, db_engine, change, reason):
    c = payments_api
    row = order(c)
    response = deliver(c, event(row, **change))
    assert response.status_code == 200, response.text
    with session_scope(db_engine) as db:
        assert db.scalar(select(PaymentEvent.reason)) == reason
        assert db.scalar(select(func.count()).select_from(Subscription)) == 0
    assert c.get(f"/payments/orders/{row['id']}").json()["status"] == "pending"


def test_atomic_failure_rolls_back_event_then_retry_succeeds(payments_api, db_engine):
    c = payments_api
    payload = event(order(c))
    with db_engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE subscriptions ADD CONSTRAINT test_reject CHECK (device_limit <> 2)")
        )
    try:
        assert deliver(c, payload).status_code == 409
        with session_scope(db_engine) as db:
            assert db.scalar(select(func.count()).select_from(PaymentEvent)) == 0
            assert db.scalar(select(PaymentOrder.status)) == "pending"
    finally:
        with db_engine.begin() as connection:
            connection.execute(text("ALTER TABLE subscriptions DROP CONSTRAINT test_reject"))
    assert deliver(c, payload).status_code == 200


def test_delayed_delivery_and_concurrent_renewals(payments_api, db_engine):
    c = payments_api
    rows = [order(c), order(c)]
    old = datetime.now(UTC) - timedelta(hours=2)
    with session_scope(db_engine) as db:
        first = db.get(PaymentOrder, uuid.UUID(rows[0]["id"]))
        first.created_at, first.expires_at = old, old + timedelta(minutes=30)
    assert c.get(f"/payments/orders/{rows[0]['id']}").json()["status"] == "expired"
    first_event = event(
        rows[0],
        transactionDate=(old + timedelta(minutes=10))
        .astimezone(timezone(timedelta(hours=7)))
        .strftime("%Y-%m-%d %H:%M:%S"),
    )
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda p: deliver(c, p), [first_event, event(rows[1])]))
    assert [r.status_code for r in results] == [200, 200]
    with session_scope(db_engine) as db:
        grants = list(db.scalars(select(Subscription).order_by(Subscription.starts_at)))
        assert len(grants) == 2 and grants[0].ends_at == grants[1].starts_at
        assert grants[1].ends_at - grants[0].starts_at == timedelta(days=60)


def test_order_idor_csrf_draft_disabled_and_paid_redirect_ignored(payments_api, db_engine):
    c = payments_api
    row = order(c)
    password = "Another user password 123!"
    c.post(
        "/auth/register",
        json={"email": "billing@example.com", "display_name": "Billing", "password": password},
    )
    c.post("/auth/login", json={"email": "billing@example.com", "password": password})
    assert c.get(f"/payments/orders/{row['id']}?status=paid").status_code == 404
    assert c.get("/payments/orders").json()["total"] == 0
    assert c.get("/admin/payment-events").status_code == 403
    with session_scope(db_engine) as db:
        db.get(Plan, "vip").is_available_for_purchase = False
    assert (
        c.post(
            "/payments/orders", json={"plan_code": "vip", "idempotency_key": str(uuid.uuid4())}
        ).status_code
        == 409
    )
    c.headers.pop("X-CSRF-Token")
    assert (
        c.post(
            "/payments/orders", json={"plan_code": "premium", "idempotency_key": str(uuid.uuid4())}
        ).status_code
        == 403
    )
    c.app.state.settings.payment_mode = "disabled"
    assert not any(p["available"] for p in c.get("/payments/plans").json()["items"])
    assert deliver(c, event(row)).status_code == 503


def test_stage10_rollback_preserves_draft_prices(db_engine):
    config = Config("alembic.ini")
    command.downgrade(config, "0008_reader")
    migrate_and_seed()
    command.check(config)
    with session_scope(db_engine) as db:
        assert db.get(Plan, "vip").price_vnd is None
