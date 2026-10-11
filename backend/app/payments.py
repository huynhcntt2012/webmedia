"""Sandbox-only billing. No client callback can mark an order paid."""

import re
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from starlette.concurrency import run_in_threadpool

from app.admin_catalogue import DB
from app.auth import require_admin, write_guard
from app.models import AuditEvent, PaymentEvent, PaymentOrder, Plan, Subscription, User
from app.payment_security import parse_event, valid_signature
from app.playback import Viewer

router = APIRouter(tags=["sandbox billing"])


def now():
    return datetime.now(UTC)


def enabled(request):
    settings = request.app.state.settings
    if settings.payment_mode != "sandbox":
        raise HTTPException(503, "Thanh toán thử nghiệm chưa được cấu hình.")
    return settings


def purchasable(plan):
    return bool(
        plan
        and plan.code != "free"
        and plan.is_active
        and plan.is_available_for_purchase
        and plan.price_vnd
        and 0 < plan.price_vnd <= 1000000000
        and plan.duration_days
        and 1 <= plan.duration_days <= 366
        and plan.device_limit
        and 1 <= plan.device_limit <= 20
    )


def order_view(row):
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "plan_code",
            "payment_code",
            "environment",
            "currency",
            "amount_vnd",
            "duration_days",
            "device_limit",
            "created_at",
            "expires_at",
            "paid_at",
        )
    } | {
        "status": "expired" if row.status == "pending" and row.expires_at <= now() else row.status,
        "receiver": {"bank": row.bank, "account": row.account, "sub_account": row.sub_account},
    }


def user_lock(db, identifier):
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 10))"), {"key": str(identifier)}
    )


@router.get("/payments/plans")
def plans(request: Request, db: DB):
    return {
        "mode": request.app.state.settings.payment_mode,
        "items": [
            {
                key: getattr(p, key)
                for key in ("code", "name", "price_vnd", "duration_days", "device_limit")
            }
            | {"available": purchasable(p) and request.app.state.settings.payment_mode == "sandbox"}
            for p in db.scalars(select(Plan).order_by(Plan.price_vnd.asc().nullsfirst(), Plan.code))
        ],
    }


class OrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_code: Literal["vip", "premium"]
    idempotency_key: uuid.UUID


@router.post("/payments/orders", status_code=201, dependencies=[Depends(write_guard)])
def create_order(data: OrderInput, actor: Viewer, request: Request, db: DB):
    settings = enabled(request)
    user_lock(db, actor.id)
    old = db.scalar(
        select(PaymentOrder).where(
            PaymentOrder.user_id == actor.id, PaymentOrder.idempotency_key == data.idempotency_key
        )
    )
    if old:
        if old.plan_code != data.plan_code:
            raise HTTPException(409, "Mã yêu cầu đã dùng cho gói khác.")
        return order_view(old)
    plan = db.get(Plan, data.plan_code)
    if not purchasable(plan):
        raise HTTPException(409, "Gói này còn ở trạng thái nháp, chưa mở thanh toán.")
    pending = db.scalar(
        select(func.count())
        .select_from(PaymentOrder)
        .where(
            PaymentOrder.user_id == actor.id,
            PaymentOrder.status == "pending",
            PaymentOrder.expires_at > now(),
        )
    )
    if pending >= 5:
        raise HTTPException(429, "Bạn đã có 5 đơn chờ. Kiểm tra đơn hiện có hoặc chờ hết hạn.")
    order = PaymentOrder(
        user_id=actor.id,
        plan_code=plan.code,
        idempotency_key=data.idempotency_key,
        payment_code="SUNI" + secrets.token_hex(12).upper(),
        amount_vnd=plan.price_vnd,
        duration_days=plan.duration_days,
        device_limit=plan.device_limit,
        bank=settings.sepay_bank,
        account=settings.sepay_account,
        sub_account=settings.sepay_sub_account,
        expires_at=now() + timedelta(minutes=30),
    )
    db.add(order)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="create",
            entity_type="payment_order",
            entity_id=order.id,
            changed_fields=["plan_code"],
        )
    )
    return order_view(order)


@router.get("/payments/orders")
def orders(actor: Viewer, db: DB, page: int = Query(1, ge=1, le=1000)):
    rows = db.scalars(
        select(PaymentOrder)
        .where(PaymentOrder.user_id == actor.id)
        .order_by(PaymentOrder.created_at.desc(), PaymentOrder.id)
        .offset((page - 1) * 20)
        .limit(20)
    )
    return {
        "items": [order_view(row) for row in rows],
        "page": page,
        "total": db.scalar(
            select(func.count()).select_from(PaymentOrder).where(PaymentOrder.user_id == actor.id)
        ),
    }


@router.get("/payments/orders/{identifier}")
def order(identifier: uuid.UUID, actor: Viewer, db: DB):
    row = db.scalar(
        select(PaymentOrder).where(PaymentOrder.id == identifier, PaymentOrder.user_id == actor.id)
    )
    if not row:
        raise HTTPException(404, "Không tìm thấy đơn.")
    return order_view(row)


@router.get("/payments/subscriptions")
def subscriptions(actor: Viewer, db: DB):
    rows = db.scalars(
        select(Subscription)
        .where(Subscription.user_id == actor.id, Subscription.ends_at > now())
        .order_by(Subscription.starts_at)
        .limit(100)
    )
    return {
        "items": [
            {
                key: getattr(row, key)
                for key in (
                    "id",
                    "order_id",
                    "plan_code",
                    "environment",
                    "starts_at",
                    "ends_at",
                    "device_limit",
                )
            }
            | {"status": "scheduled" if row.starts_at > now() else "active"}
            for row in rows
        ]
    }


def rejection(order, payload):
    if not order:
        return "unknown_order"
    if payload.transferType != "in":
        return "outgoing"
    if (payload.gateway, payload.accountNumber, payload.subAccount or "") != (
        order.bank,
        order.account,
        order.sub_account,
    ):
        return "wrong_receiver"
    if payload.transferAmount != order.amount_vnd or payload.currency != order.currency:
        return "wrong_amount_currency"
    if payload.code != order.payment_code or re.findall(
        r"(?<![A-Z0-9])SUNI[A-Z0-9]+(?![A-Z0-9])", payload.content
    ) != [order.payment_code]:
        return "ambiguous_code"
    if not order.created_at.replace(
        microsecond=0
    ) <= payload.occurred_at() <= order.expires_at or payload.occurred_at() > now() + timedelta(
        seconds=5
    ):
        return "outside_order_window"
    if order.status == "paid":
        return "extra_payment"
    return None


def accept_event(db, payload):
    digest = payload.digest()
    event_id = db.scalar(
        insert(PaymentEvent)
        .values(provider_transaction_id=payload.id, payload_sha256=digest)
        .on_conflict_do_nothing(index_elements=["environment", "provider_transaction_id"])
        .returning(PaymentEvent.id)
    )
    if event_id is None:
        previous = db.scalar(
            select(PaymentEvent).where(
                PaymentEvent.provider_transaction_id == payload.id,
                PaymentEvent.environment == "sandbox",
            )
        )
        if previous.payload_sha256 != digest:
            raise HTTPException(409, "Transaction identity conflict")
        return {"success": True}
    event = db.get(PaymentEvent, event_id)
    order = db.scalar(
        select(PaymentOrder).where(PaymentOrder.payment_code == payload.code).with_for_update()
    )
    event.order_id = order.id if order else None
    reason = rejection(order, payload)
    if not reason:
        user = db.get(User, order.user_id) if order.user_id else None
        if not user or not user.is_active:
            reason = "inactive_owner"
    if reason:
        event.status, event.reason = "rejected", reason
        return {"success": True}
    user_lock(db, order.user_id)
    end = db.scalar(
        select(func.max(Subscription.ends_at)).where(
            Subscription.user_id == order.user_id,
            Subscription.plan_code == order.plan_code,
            Subscription.environment == "sandbox",
        )
    )
    start = max(now(), end) if end else now()
    db.add(
        Subscription(
            order_id=order.id,
            user_id=order.user_id,
            plan_code=order.plan_code,
            starts_at=start,
            ends_at=start + timedelta(days=order.duration_days),
            device_limit=order.device_limit,
        )
    )
    order.status, order.paid_at = "paid", now()
    event.status = "accepted"
    db.add(
        AuditEvent(
            actor_id=None,
            action="paid",
            entity_type="payment_order",
            entity_id=order.id,
            changed_fields=["status", "paid_at"],
        )
    )
    db.flush()
    return {"success": True}


@router.post("/payments/sepay/webhook")
async def webhook(request: Request, db: DB):
    settings = enabled(request)
    body = await request.body()
    if not valid_signature(
        settings.sepay_webhook_secret.get_secret_value(),
        request.headers.get("x-sepay-timestamp", ""),
        request.headers.get("x-sepay-signature", ""),
        body,
        int(time.time()),
    ):
        raise HTTPException(401, "Invalid webhook signature")
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise HTTPException(415, "JSON webhook required")
    try:
        payload = parse_event(body)
    except (ValueError, UnicodeError):
        raise HTTPException(422, "Invalid bank event") from None
    return await run_in_threadpool(accept_event, db, payload)


@router.get("/admin/payment-events", dependencies=[Depends(require_admin)])
def events(db: DB, page: int = Query(1, ge=1, le=1000)):
    rows = db.scalars(
        select(PaymentEvent)
        .order_by(PaymentEvent.created_at.desc(), PaymentEvent.id)
        .offset((page - 1) * 20)
        .limit(20)
    )
    return {
        "items": [
            {
                key: getattr(row, key)
                for key in (
                    "id",
                    "provider_transaction_id",
                    "order_id",
                    "environment",
                    "status",
                    "reason",
                    "created_at",
                )
            }
            for row in rows
        ],
        "page": page,
        "total": db.scalar(select(func.count()).select_from(PaymentEvent)),
    }
