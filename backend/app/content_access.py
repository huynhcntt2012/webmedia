"""Origin-authorized private media; no bearer URLs, no sandbox paid entitlement."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, select, text, update

from app.admin_catalogue import DB, Actor
from app.auth import current_user, require_admin, write_guard
from app.models import AuditEvent, AuthSession, ContentDevice, ContentGrant, User

router = APIRouter(tags=["content access"])
Viewer = Annotated[User, Depends(current_user)]
RANK = {"free": 0, "vip": 1, "premium": 2}


def now():
    return datetime.now(UTC)


def access(db, user):
    if user.role == "admin":
        return {"plan": "premium", "device_limit": 10, "expires_at": None, "source": "admin"}
    grant = db.scalar(
        select(ContentGrant)
        .where(
            ContentGrant.user_id == user.id,
            ContentGrant.revoked_at.is_(None),
            ContentGrant.starts_at <= now(),
            ContentGrant.expires_at > now(),
        )
        .order_by(
            case((ContentGrant.plan_code == "premium", 2), else_=1).desc(),
            ContentGrant.expires_at.desc(),
            ContentGrant.id,
        )
        .limit(1)
    )
    return {
        "plan": grant.plan_code if grant else "free",
        "device_limit": grant.device_limit if grant else 2,
        "expires_at": grant.expires_at if grant else None,
        "source": "admin_grant" if grant else "free",
    }


def entitled(db, content, user):
    return RANK[access(db, user)["plan"]] >= RANK[content.required_plan_code]


def active_devices(db, user_id):
    return list(
        db.scalars(
            select(ContentDevice)
            .join(AuthSession, AuthSession.id == ContentDevice.session_id)
            .where(
                ContentDevice.user_id == user_id,
                ContentDevice.expires_at > now(),
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now(),
            )
            .order_by(ContentDevice.created_at, ContentDevice.session_id)
        )
    )


def content_user(request: Request, actor: Viewer, db: DB):
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 11))"), {"key": str(actor.id)}
    )
    sid = request.state.auth_session_id
    family = db.get(AuthSession, sid)
    if not family or family.revoked_at or family.expires_at <= now():
        raise HTTPException(401, "Phiên đã bị thu hồi.")
    permitted = access(db, actor)["device_limit"]
    current = db.get(ContentDevice, sid)
    active = active_devices(db, actor.id)
    admitted = [row.session_id for row in active[:permitted]]
    if (current and current.expires_at > now() and sid not in admitted) or (
        sid not in admitted and len(active) >= permitted
    ):
        raise HTTPException(
            403, "Đã đủ thiết bị xem/đọc đồng thời. Mở /devices để thu hồi phiên cũ."
        )
    if current is None:
        current = ContentDevice(session_id=sid, user_id=actor.id, expires_at=now())
        db.add(current)
        db.add(
            AuditEvent(
                actor_id=actor.id,
                action="admit",
                entity_type="content_device",
                entity_id=sid,
                changed_fields=[],
            )
        )
    # Admission is atomic; renewal writes at most once per minute per session.
    if current.expires_at < now() + timedelta(minutes=4):
        current.expires_at = min(now() + timedelta(minutes=5), family.expires_at)
    return actor


ContentViewer = Annotated[User, Depends(content_user)]


@router.get("/content/access")
def current_access(actor: Viewer, db: DB):
    return access(db, actor)


@router.get("/content/devices")
def devices(request: Request, actor: Viewer, db: DB):
    return {
        "items": [
            {
                "id": row.session_id,
                "created_at": row.created_at,
                "expires_at": row.expires_at,
                "current": row.session_id == request.state.auth_session_id,
            }
            for row in active_devices(db, actor.id)
        ]
    }


@router.delete(
    "/content/devices/{identifier}", status_code=204, dependencies=[Depends(write_guard)]
)
def revoke_device(identifier: uuid.UUID, actor: Viewer, db: DB):
    row = db.get(ContentDevice, identifier)
    if not row or row.user_id != actor.id:
        raise HTTPException(404, "Không tìm thấy thiết bị.")
    db.execute(
        update(AuthSession)
        .where(AuthSession.id == identifier, AuthSession.user_id == actor.id)
        .values(revoked_at=now())
    )
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="revoke",
            entity_type="content_device",
            entity_id=identifier,
            changed_fields=[],
        )
    )


class GrantInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: uuid.UUID
    plan_code: Literal["vip", "premium"]
    days: int = Field(ge=1, le=366, strict=True)
    device_limit: int = Field(ge=1, le=20, strict=True)


@router.post("/admin/content-grants", status_code=201)
def grant(data: GrantInput, actor: Actor, db: DB):
    user = db.get(User, data.user_id)
    if not user or not user.is_active:
        raise HTTPException(404, "Không tìm thấy tài khoản hoạt động.")
    row = ContentGrant(
        user_id=user.id,
        plan_code=data.plan_code,
        device_limit=data.device_limit,
        starts_at=now(),
        expires_at=now() + timedelta(days=data.days),
    )
    db.add(row)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="grant",
            entity_type="content_grant",
            entity_id=row.id,
            changed_fields=["plan_code", "expires_at", "device_limit"],
        )
    )
    return {"id": row.id, "expires_at": row.expires_at}


@router.get("/admin/content-grants", dependencies=[Depends(require_admin)])
def grants(user_id: uuid.UUID, db: DB):
    return {
        "items": [
            {
                "id": row.id,
                "plan_code": row.plan_code,
                "expires_at": row.expires_at,
                "revoked_at": row.revoked_at,
            }
            for row in db.scalars(
                select(ContentGrant)
                .where(ContentGrant.user_id == user_id)
                .order_by(ContentGrant.expires_at.desc())
                .limit(100)
            )
        ]
    }


@router.delete("/admin/content-grants/{identifier}", status_code=204)
def revoke_grant(identifier: uuid.UUID, actor: Actor, db: DB):
    row = db.get(ContentGrant, identifier, with_for_update=True)
    if not row:
        raise HTTPException(404, "Không tìm thấy quyền.")
    row.revoked_at = now()
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="revoke",
            entity_type="content_grant",
            entity_id=row.id,
            changed_fields=["revoked_at"],
        )
    )
