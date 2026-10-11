"""Cookie authentication with CSRF, Redis throttling and transactional token rotation."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator
from redis.exceptions import RedisError
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.database import session_scope
from app.models import AuthSession, RefreshToken, User
from app.security import (
    ACCESS_SECONDS,
    DUMMY_HASH,
    SESSION_SECONDS,
    access_token,
    csrf_token,
    decode_access,
    digest,
    keyed_digest,
    passwords,
    valid_csrf,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["authentication"])
admin_router = APIRouter(prefix="/admin", tags=["authorization"])
GENERIC_LOGIN = "Email hoặc mật khẩu không đúng."
GENERIC_REGISTER = "Yêu cầu đã được xử lý. Bạn có thể đăng nhập bằng thông tin của mình."
LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr = Field(max_length=254)
    password: SecretStr = Field(min_length=12, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def canonical_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class RegisterInput(LoginInput):
    display_name: str = Field(min_length=1, max_length=120)

    @field_validator("display_name")
    @classmethod
    def trim_name(cls, value):
        if not value.strip():
            raise ValueError("Display name required")
        return value.strip()


def cookie_name(request: Request, purpose: str) -> str:
    prefix = "__Host-" if request.app.state.settings.app_env == "production" else ""
    return f"{prefix}suni_{purpose}"


def set_cookie(request: Request, response: Response, purpose: str, value: str, max_age: int):
    response.set_cookie(
        cookie_name(request, purpose),
        value,
        max_age=max_age,
        secure=request.app.state.settings.app_env == "production",
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_auth(request: Request, response: Response):
    for purpose in ("access", "refresh"):
        response.delete_cookie(
            cookie_name(request, purpose),
            path="/",
            httponly=True,
            secure=request.app.state.settings.app_env == "production",
            samesite="lax",
        )


def throttle(request: Request, bucket: str, value: str, limit: int):
    settings = request.app.state.settings
    key = "suni:auth:" + bucket + ":" + keyed_digest(settings.app_secret.get_secret_value(), value)
    try:
        count = request.app.state.auth_cache.eval(LIMIT_SCRIPT, 1, key, 60)
    except RedisError:
        raise HTTPException(503, "Dịch vụ xác thực tạm thời không sẵn sàng.") from None
    if count > limit:
        raise HTTPException(
            429, "Quá nhiều yêu cầu. Vui lòng thử lại sau.", headers={"Retry-After": "60"}
        )


def write_guard(request: Request):
    settings = request.app.state.settings
    if request.headers.get("origin") != settings.public_origin:
        raise HTTPException(403, "Origin không hợp lệ.")
    if not valid_csrf(
        settings.app_secret.get_secret_value(),
        request.cookies.get(cookie_name(request, "csrf"), ""),
        request.headers.get("x-csrf-token", ""),
    ):
        raise HTTPException(403, "CSRF token không hợp lệ hoặc hết hạn.")
    # Forwarded headers are deliberately ignored; requests via web share its IP limit.
    ip = request.client.host if request.client else "unknown"
    throttle(request, "write-ip", ip, settings.auth_ip_limit)


def summary(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "plan_code": user.plan_code,
    }


def issue(request: Request, response: Response, user_id, family, raw: str):
    secret = request.app.state.settings.app_secret.get_secret_value()
    set_cookie(
        request, response, "access", access_token(secret, user_id, family.id), ACCESS_SECONDS
    )
    remaining = max(0, int((family.expires_at - datetime.now(UTC)).total_seconds()))
    set_cookie(request, response, "refresh", raw, remaining)


@router.get("/csrf")
def csrf(request: Request, response: Response):
    ip = request.client.host if request.client else "unknown"
    throttle(request, "csrf-ip", ip, 120)
    token = csrf_token(request.app.state.settings.app_secret.get_secret_value())
    set_cookie(request, response, "csrf", token, 3600)
    return {"csrf_token": token}


@router.post("/register", status_code=202, dependencies=[Depends(write_guard)])
def register(data: RegisterInput, request: Request):
    throttle(request, "account", str(data.email), request.app.state.settings.auth_account_limit)
    # Always hash, including duplicate registrations; no account existence response.
    encoded = passwords.hash(data.password.get_secret_value())
    with session_scope(request.app.state.auth_engine) as db:
        db.execute(
            insert(User)
            .values(email=str(data.email), display_name=data.display_name, password_hash=encoded)
            .on_conflict_do_nothing(index_elements=["email"])
        )
    return {"message": GENERIC_REGISTER}


@router.post("/login", dependencies=[Depends(write_guard)])
def login(data: LoginInput, request: Request, response: Response):
    throttle(request, "account", str(data.email), request.app.state.settings.auth_account_limit)
    raw = secrets.token_urlsafe(48)
    with session_scope(request.app.state.auth_engine) as db:
        user = db.scalar(select(User).where(User.email == str(data.email)))
        valid = verify_password(
            data.password.get_secret_value(), user.password_hash if user else DUMMY_HASH
        )
        if not user or not valid or not user.is_active:
            raise HTTPException(401, GENERIC_LOGIN)
        family = AuthSession(
            user_id=user.id, expires_at=datetime.now(UTC) + timedelta(seconds=SESSION_SECONDS)
        )
        db.add(family)
        db.flush()
        db.add(RefreshToken(token_hash=digest(raw), session_id=family.id))
        result = summary(user)
    issue(request, response, user.id, family, raw)
    return {"user": result}


@router.post("/refresh", dependencies=[Depends(write_guard)])
def refresh(request: Request, response: Response):
    raw = request.cookies.get(cookie_name(request, "refresh"), "")
    if len(raw) != 64:
        raise HTTPException(401, "Phiên đăng nhập không hợp lệ.")
    denied = False
    replacement = secrets.token_urlsafe(48)
    with session_scope(request.app.state.auth_engine) as db:
        token = db.get(RefreshToken, digest(raw))
        if token is None:
            raise HTTPException(401, "Phiên đăng nhập không hợp lệ.")
        family = db.scalar(
            select(AuthSession).where(AuthSession.id == token.session_id).with_for_update()
        )
        db.refresh(token)  # Read consumed_at AFTER acquiring the family lock (concurrent refresh).
        user = db.get(User, family.user_id)
        now = datetime.now(UTC)
        if family.revoked_at or family.expires_at <= now or token.consumed_at or not user.is_active:
            family.revoked_at = family.revoked_at or now
            denied = True
        else:
            token.consumed_at = now
            db.add(RefreshToken(token_hash=digest(replacement), session_id=family.id))
    # Commit revocation before returning 401; an exception inside the transaction would undo it.
    if denied:
        response.status_code = 401
        clear_auth(request, response)
        return {"detail": "Phiên đăng nhập đã hết hạn hoặc bị thu hồi. Vui lòng đăng nhập lại."}
    issue(request, response, user.id, family, replacement)
    return {"user": summary(user)}


def current_user(request: Request):
    token = request.cookies.get(cookie_name(request, "access"), "")
    try:
        claims = decode_access(request.app.state.settings.app_secret.get_secret_value(), token)
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise HTTPException(401, "Vui lòng đăng nhập.") from None
    with session_scope(request.app.state.auth_engine) as db:
        family = db.get(AuthSession, uuid.UUID(claims["sid"]))
        user = db.get(User, uuid.UUID(claims["sub"]))
        if (
            not family
            or not user
            or family.user_id != user.id
            or family.revoked_at
            or family.expires_at <= datetime.now(UTC)
            or not user.is_active
        ):
            raise HTTPException(401, "Phiên đăng nhập đã hết hạn.")
        request.state.auth_session_id = family.id
        return user


def require_admin(user: Annotated[User, Depends(current_user)]):
    if user.role != "admin":
        raise HTTPException(403, "Bạn không có quyền quản trị.")
    return user


@router.get("/me")
def me(user: Annotated[User, Depends(current_user)]):
    return {"user": summary(user)}


@admin_router.get("/check")
def admin_check(user: Annotated[User, Depends(require_admin)]):
    return {"authorized": True, "user": summary(user)}


@router.post("/logout", status_code=204, dependencies=[Depends(write_guard)])
def logout(request: Request, response: Response):
    raw = request.cookies.get(cookie_name(request, "refresh"), "")
    with session_scope(request.app.state.auth_engine) as db:
        token = db.get(RefreshToken, digest(raw)) if len(raw) == 64 else None
        session_id = token.session_id if token else None
        if session_id is None:
            try:
                claims = decode_access(
                    request.app.state.settings.app_secret.get_secret_value(),
                    request.cookies.get(cookie_name(request, "access"), ""),
                )
                session_id = uuid.UUID(claims["sid"])
            except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
                pass
        if session_id:
            db.execute(
                update(AuthSession)
                .where(AuthSession.id == session_id)
                .values(revoked_at=datetime.now(UTC))
            )
    clear_auth(request, response)


@router.post("/logout-all", status_code=204, dependencies=[Depends(write_guard)])
def logout_all(request: Request, response: Response, user: Annotated[User, Depends(current_user)]):
    with session_scope(request.app.state.auth_engine) as db:
        db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user.id)
            .values(revoked_at=datetime.now(UTC))
        )
    clear_auth(request, response)
