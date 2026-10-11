import time
import uuid

import jwt
import pytest

from app.auth import RegisterInput
from app.security import (
    access_token,
    csrf_token,
    decode_access,
    passwords,
    valid_csrf,
    verify_password,
)

SECRET = "a" * 64


def test_argon2_hash_and_wrong_password():
    hashed = passwords.hash("a long correct password")
    assert hashed.startswith("$argon2id$")
    assert verify_password("a long correct password", hashed)
    assert not verify_password("incorrect password", hashed)
    assert not verify_password("password", "$argon2id$invalid")


def test_access_claims_expiry_and_signature():
    token = access_token(SECRET, uuid.uuid4(), uuid.uuid4())
    claims = decode_access(SECRET, token)
    assert claims["exp"] - claims["iat"] == 300
    for replacement in (
        {"exp": int(time.time()) - 1},
        {"aud": "wrong"},
        {"iss": "other"},
        {"typ": "refresh"},
    ):
        with pytest.raises(jwt.InvalidTokenError):
            decode_access(SECRET, jwt.encode(claims | replacement, SECRET, algorithm="HS256"))
    with pytest.raises(jwt.InvalidTokenError):
        decode_access("b" * 64, token)


def test_csrf_signature_and_cookie_binding():
    token = csrf_token(SECRET)
    assert valid_csrf(SECRET, token, token)
    assert not valid_csrf(SECRET, token, csrf_token(SECRET))
    assert not valid_csrf("b" * 64, token, token)
    assert not valid_csrf(SECRET, "garbage", "garbage")


def test_registration_normalizes_identity_and_rejects_roles():
    data = {
        "email": " Alice@Example.com ",
        "password": "long correct password",
        "display_name": " Alice ",
    }
    result = RegisterInput(**data)
    assert result.email == "alice@example.com" and result.display_name == "Alice"
    assert "long correct password" not in repr(result)
    with pytest.raises(ValueError):
        RegisterInput(**(data | {"role": "admin"}))
