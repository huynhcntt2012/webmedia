"""Reproducible local acceptance; only destroys the named isolated test project."""
import os
import secrets
import subprocess

from check_production_runtime import COMPOSE, ROOT


def main():
    directory = ROOT / "test-results"
    directory.mkdir(exist_ok=True)
    environment = directory / "stage12.env"
    if not environment.exists():
        values = {name: secrets.token_hex(32) for name in ["APP_SECRET", "POSTGRES_PASSWORD",
                  "REDIS_PASSWORD", "MIGRATOR_PASSWORD", "RUNTIME_PASSWORD"]}
        values.update(POSTGRES_DB="suni_test", POSTGRES_USER="suni")
        fd = os.open(environment, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("".join(f"{key}={value}\n" for key, value in values.items()))
    # Fixed isolated project; never accept an arbitrary project from CLI or environment.
    assert COMPOSE[COMPOSE.index("-p") + 1] == "suni-production-check"
    try:
        subprocess.run(COMPOSE + ["down", "-v"], cwd=ROOT, check=True)
        subprocess.run(COMPOSE + ["up", "--build", "-d", "--wait", "--wait-timeout", "180"],
                       cwd=ROOT, check=True)
        import check_production_runtime
        check_production_runtime.main()
    finally:
        subprocess.run(COMPOSE + ["down", "-v"], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
