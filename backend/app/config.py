import re
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    app_secret: SecretStr
    database_url: SecretStr
    redis_url: SecretStr
    public_origin: str = "http://localhost:3000"
    allowed_hosts: str = "localhost,127.0.0.1,api"
    readiness_timeout_seconds: float = 3.0
    auth_ip_limit: int = Field(default=60, ge=1, le=10000)
    auth_account_limit: int = Field(default=10, ge=1, le=10000)
    poster_allowed_hosts: str = ""
    media_root: str = "/var/lib/suni-media"
    comic_quota_bytes: int = Field(default=2147483648, ge=1048576)
    upload_max_bytes: int = Field(default=1073741824, ge=1048576, le=2147483648)
    media_quota_bytes: int = Field(default=21474836480, ge=4294967296)
    upload_active_limit: int = Field(default=3, ge=1, le=10)
    payment_mode: Literal["disabled", "sandbox"] = "disabled"
    sepay_webhook_secret: SecretStr = SecretStr("")
    sepay_bank: str = Field(default="", max_length=80)
    sepay_account: str = Field(default="", max_length=40)
    sepay_sub_account: str = Field(default="", max_length=40)

    @model_validator(mode="after")
    def payment_config(self):
        if self.payment_mode == "sandbox":
            if self.app_env == "production":
                raise ValueError("Sandbox payments cannot run in production")
            if len(self.sepay_webhook_secret.get_secret_value()) < 32:
                raise ValueError(
                    "Sandbox webhook needs an independent secret of at least 32 characters"
                )
            if self.sepay_webhook_secret == self.app_secret:
                raise ValueError("Webhook secret must differ from app secret")
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 ]{1,79}", self.sepay_bank):
                raise ValueError("Sandbox bank must be an explicit bank identifier")
            if not re.fullmatch(r"[A-Za-z0-9]{4,40}", self.sepay_account):
                raise ValueError("Sandbox receiver account is required")
            if self.sepay_sub_account and not re.fullmatch(
                r"[A-Za-z0-9]{1,40}", self.sepay_sub_account
            ):
                raise ValueError("Invalid sandbox subaccount")
        return self

    @field_validator("poster_allowed_hosts")
    @classmethod
    def poster_hosts(cls, value: str) -> str:
        hosts = [host.strip().lower() for host in value.split(",") if host.strip()]
        if any(
            not re.fullmatch(
                r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+", host
            )
            or host.replace(".", "").isdigit()
            for host in hosts
        ):
            raise ValueError("Poster hosts must be explicit DNS names, without scheme or wildcard")
        return ",".join(hosts)

    @field_validator("app_secret")
    @classmethod
    def strong_secret(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if len(raw) < 32 or raw.lower() in {"generate_me", "changeme"}:
            raise ValueError("APP_SECRET must be at least 32 characters, generated randomly")
        return value

    @field_validator("database_url", "redis_url")
    @classmethod
    def valid_dependency_url(cls, value: SecretStr, info):
        parsed = urlsplit(value.get_secret_value())
        permitted = (
            {"postgresql+psycopg"} if info.field_name == "database_url" else {"redis", "rediss"}
        )
        if parsed.scheme not in permitted or not parsed.hostname or not parsed.password:
            raise ValueError("Dependency URL requires a supported scheme, host and password")
        return value

    @field_validator("allowed_hosts")
    @classmethod
    def exact_hosts(cls, value: str) -> str:
        hosts = [host.strip() for host in value.split(",")]
        if not hosts or any(not host or "*" in host or "/" in host for host in hosts):
            raise ValueError("ALLOWED_HOSTS must list explicit hostnames")
        return ",".join(hosts)

    @field_validator("public_origin")
    @classmethod
    def valid_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("PUBLIC_ORIGIN requires an exact HTTP(S) origin, no trailing slash")
        return value

    @field_validator("readiness_timeout_seconds")
    @classmethod
    def bounded_timeout(cls, value: float) -> float:
        if not 0.1 <= value <= 10:
            raise ValueError("Readiness timeout must be between 0.1 and 10 seconds")
        return value

    @model_validator(mode="after")
    def production_config(self):
        if self.app_env == "production" and not self.public_origin.startswith("https://"):
            raise ValueError("Production requires an HTTPS public origin")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
