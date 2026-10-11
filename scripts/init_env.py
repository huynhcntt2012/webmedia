"""Create local secrets without overwriting an existing configuration."""

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    template = (ROOT / ".env.example").read_text(encoding="utf-8")
    for key in (
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "APP_SECRET",
        "MIGRATOR_PASSWORD",
        "RUNTIME_PASSWORD",
    ):
        template = template.replace(
            f"{key}=GENERATE_ME", f"{key}={secrets.token_hex(32)}"
        )
    try:
        with (ROOT / ".env").open("x", encoding="utf-8") as output:
            output.write(template)
    except FileExistsError:
        raise SystemExit(".env exists; left unchanged.") from None
    print("Created .env with independent random secrets. Do not commit this file.")


if __name__ == "__main__":
    main()
