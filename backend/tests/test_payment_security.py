import hashlib
import hmac
import json

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.payment_security import parse_event, valid_signature


def test_hmac_raw_bytes_timestamp_and_constant_format():
    secret, timestamp, body = "s" * 48, "1791630000", b'{"code":"SUNI123", "x":1}'
    signature = (
        "sha256="
        + hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    )
    assert valid_signature(secret, timestamp, signature, body, int(timestamp))
    for ts, sig, raw, current in [
        (timestamp, signature, body + b" ", int(timestamp)),
        (timestamp, signature, body, int(timestamp) + 301),
        (timestamp, signature, body, int(timestamp) - 301),
        ("000", signature, body, int(timestamp)),
        (timestamp, signature.upper(), body, int(timestamp)),
        (timestamp, "x", body, int(timestamp)),
    ]:
        assert not valid_signature(secret, ts, sig, raw, current)


@pytest.mark.parametrize(
    "override",
    [
        {"id": True},
        {"transferAmount": 1.1},
        {"transferAmount": "10"},
        {"transferAmount": -1},
        {"currency": "USD"},
        {"transactionDate": "2026-02-30 10:00:00"},
        {"transferType": "credit"},
    ],
)
def test_invalid_bank_payload(override):
    body = {
        "id": 1,
        "gateway": "TestBank",
        "accountNumber": "1234",
        "transactionDate": "2026-10-10 10:00:00",
        "content": "SUNI1",
        "transferType": "in",
        "transferAmount": 10,
    } | override
    with pytest.raises(ValueError):
        parse_event(json.dumps(body).encode())


def test_duplicate_json_keys():
    with pytest.raises(ValueError):
        parse_event(b'{"id":1,"id":2}')


@pytest.mark.parametrize(
    "override",
    [
        {},
        {"sepay_webhook_secret": "s" * 48},
        {
            "app_env": "production",
            "public_origin": "https://example.com",
            "sepay_webhook_secret": "s" * 48,
            "sepay_bank": "TestBank",
            "sepay_account": "123456",
        },
    ],
)
def test_payment_configuration_fails_closed(settings, override):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **(settings.model_dump() | {"payment_mode": "sandbox"} | override))
