import hashlib
import hmac
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

passwords = PasswordHash.recommended()
DUMMY_HASH = passwords.hash(secrets.token_urlsafe(32))
ACCESS_SECONDS = 300
SESSION_SECONDS = 30 * 24 * 3600


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def keyed_digest(secret: str, value: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def verify_password(password: str, encoded: str) -> bool:
    try:
        return passwords.verify(password, encoded)
    except Exception:
        # Malformed legacy data must fail closed, never return a hash or parser error.
        # pwdlib errors vary by backend; no exception data is logged.
        return False


def access_token(secret: str, user_id: uuid.UUID, session_id: uuid.UUID) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "sid": str(session_id),
            "jti": str(uuid.uuid4()),
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(seconds=ACCESS_SECONDS),
            "iss": "suni-api",
            "aud": "suni-web",
            "typ": "access",
        },
        secret,
        algorithm="HS256",
    )


def decode_access(secret: str, token: str) -> dict:
    claims = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        issuer="suni-api",
        audience="suni-web",
        options={"require": ["sub", "sid", "jti", "iat", "nbf", "exp", "typ"]},
    )
    if claims["typ"] != "access":
        raise jwt.InvalidTokenError("Invalid token type")
    uuid.UUID(claims["sub"])
    uuid.UUID(claims["sid"])
    return claims


def csrf_token(secret: str) -> str:
    payload = f"{int(time.time())}.{secrets.token_urlsafe(32)}"
    return f"{payload}.{keyed_digest(secret, 'csrf:' + payload)}"


def valid_csrf(secret: str, cookie: str, header: str) -> bool:
    if not cookie or len(cookie) > 200 or not hmac.compare_digest(cookie, header):
        return False
    try:
        issued, nonce, signature = cookie.split(".")
        payload = f"{issued}.{nonce}"
        return 0 <= time.time() - int(issued) < 3600 and hmac.compare_digest(
            signature, keyed_digest(secret, "csrf:" + payload)
        )
    except (ValueError, TypeError):
        return False
