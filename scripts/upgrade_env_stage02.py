"""Append only missing role secrets to an existing local .env; preserve all old values."""

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    target = ROOT / ".env"
    existing = target.read_text(encoding="utf-8")
    keys = {
        line.split("=", 1)[0].strip() for line in existing.splitlines() if "=" in line
    }
    additions = [
        f"{key}={secrets.token_hex(32)}"
        for key in ("MIGRATOR_PASSWORD", "RUNTIME_PASSWORD")
        if key not in keys
    ]
    if additions:
        with target.open("a", encoding="utf-8") as output:
            output.write("\n# Stage 02 database roles\n" + "\n".join(additions) + "\n")
    print(
        f"Added {len(additions)} missing role secrets; existing configuration preserved."
    )


if __name__ == "__main__":
    main()
