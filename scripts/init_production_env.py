"""Create separate production secrets; never reuse or print development secrets."""
import os
import secrets
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    values = {
        "APP_ENV": "production",
        "PUBLIC_ORIGIN": "https://cinema.sunifactory.com",
        "POSTGRES_DB": "suni",
        "POSTGRES_USER": "suni",
        "POSTER_ALLOWED_HOSTS": "media.sunifactory.com",
        "PAYMENT_MODE": "disabled",
    }
    for name in ("APP_SECRET", "POSTGRES_PASSWORD", "REDIS_PASSWORD",
                 "MIGRATOR_PASSWORD", "RUNTIME_PASSWORD"):
        values[name] = secrets.token_hex(32)
    path = root / ".env.production"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        output.write("".join(f"{key}={value}\n" for key, value in values.items()))
    print("Created protected .env.production; existing files are never overwritten.")


if __name__ == "__main__":
    main()
