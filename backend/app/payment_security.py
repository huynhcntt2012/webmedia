"""SePay bank-webhook JSON contract; no payment gateway/IPN mixing."""

import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def valid_signature(secret: str, timestamp: str, signature: str, body: bytes, now: int) -> bool:
    if not re.fullmatch(r"[0-9]{10}", timestamp) or abs(now - int(timestamp)) > 300:
        return False
    if not re.fullmatch(r"sha256=[0-9a-f]{64}", signature):
        return False
    expected = (
        "sha256="
        + hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


class BankEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: int = Field(gt=0, le=9223372036854775807)
    gateway: str = Field(min_length=1, max_length=80)
    transactionDate: str = Field(pattern=r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
    accountNumber: str = Field(min_length=1, max_length=40)
    subAccount: str | None = Field(default=None, max_length=40)
    code: str | None = Field(default=None, max_length=100)
    content: str = Field(max_length=4000)
    transferType: Literal["in", "out"]
    transferAmount: int = Field(gt=0, le=1000000000000)
    referenceCode: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=4000)
    accumulated: int = 0
    # The official bank-webhook amounts are VND; an explicit foreign currency must fail closed.
    currency: Literal["VND"] = "VND"

    @field_validator("transactionDate")
    @classmethod
    def valid_date(cls, value):
        datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return value

    def occurred_at(self):
        return datetime.strptime(self.transactionDate, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone(timedelta(hours=7))
        )

    def digest(self):
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


def parse_event(body: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    return BankEvent.model_validate(json.loads(body, object_pairs_hook=unique))
