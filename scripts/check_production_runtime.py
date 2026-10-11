"""Integration checks ONLY on the disposable suni-production-check Compose project."""
import hashlib
import io
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlopen

from local_ops import backup, initialize, restore_test, status

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "--env-file", "test-results/stage12.env",
           "-p", "suni-production-check", "-f", "compose.yaml", "-f", "compose.production.yaml"]


def run(*args, data=None):
    return subprocess.run(COMPOSE + list(args), input=data, capture_output=True,
                          check=True, cwd=ROOT).stdout


def sql(query, database="suni_test"):
    return run("exec", "-T", "postgres", "psql", "-U", "suni", "-d", database,
               "-v", "ON_ERROR_STOP=1", "-Atc", query).decode().strip()


def main():
    assert sql("select current_database()") == "suni_test"
    for service in ["api", "postgres", "redis"]:
        cid = run("ps", "-q", service).decode().strip()
        ports = subprocess.check_output(
            ["docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", cid])
        assert all(not value for value in json.loads(ports).values())
    with urlopen("http://127.0.0.1:8083/api/auth/csrf", timeout=10) as response:
        cookie = response.headers["Set-Cookie"]
        assert "Secure" in cookie and "HttpOnly" in cookie
        assert response.headers["Cache-Control"] == "no-store"
    with urlopen("http://127.0.0.1:8083/api/payments/plans", timeout=10) as response:
        assert json.load(response)["mode"] == "disabled"
    run("stop", "-t", "60", "web", "api", "worker", "beat")
    try:
        # A binary row plus full schema/seed exercises custom dump and restoration.
        sql("CREATE TABLE restore_probe (payload bytea); "
            "INSERT INTO restore_probe VALUES (decode('deadbeef00ff','hex'))")
        run("run", "--rm", "--no-deps", "-T", "api", "python", "-c",
            "from pathlib import Path; Path('/var/lib/suni-media/restore-probe').write_bytes(bytes(range(256)))")
        dump = run("exec", "-T", "postgres", "pg_dump", "-U", "suni", "-d", "suni_test", "-Fc")
        media = run("run", "--rm", "--no-deps", "-T", "api", "python", "-c",
                    'import sys,tarfile; t=tarfile.open(fileobj=sys.stdout.buffer,mode="w|"); '
                    't.add("/var/lib/suni-media",arcname="media"); t.close()')
        run("exec", "-T", "postgres", "createdb", "-U", "suni", "suni_restore_test")
        try:
            run("exec", "-T", "postgres", "pg_restore", "-U", "suni", "-d", "suni_restore_test",
                "--no-owner", "--no-acl", "--exit-on-error", data=dump)
            assert sql("SELECT count(*) FROM plans", "suni_restore_test") == "3"
            assert sql("SELECT version_num FROM alembic_version", "suni_restore_test") == "0010_content_access"
            assert sql("SELECT encode(payload,'hex') FROM restore_probe", "suni_restore_test") == "deadbeef00ff"
            with tarfile.open(fileobj=io.BytesIO(media)) as archive:
                restored = archive.extractfile("media/restore-probe").read()
                assert hashlib.sha256(restored).digest() == hashlib.sha256(bytes(range(256))).digest()
        finally:
            run("exec", "-T", "postgres", "dropdb", "-U", "suni", "suni_restore_test")

    finally:
        run("up", "--no-deps", "-d", "--wait", "--wait-timeout", "180", "api", "worker", "beat", "web")
    run("up", "--no-deps", "-d", "--wait", "--wait-timeout", "180", "api", "worker", "beat", "web")
    with tempfile.TemporaryDirectory(prefix="operations-", dir=ROOT / "test-results") as temp:
        directory = Path(temp) / "encrypted"
        initialize(directory)
        backup("test", directory)
        restore_test(directory)
        assert status("test", directory) == 0
        # Wrong password must fail before taking the application offline.
        password = directory / "password"
        original = password.read_bytes()
        password.write_bytes(b"wrong-test-password")
        try:
            try:
                backup("test", directory)
                raise AssertionError("Wrong password was accepted")
            except RuntimeError:
                pass
        finally:
            password.write_bytes(original)
        assert status("test", directory) == 0
    sql("DROP TABLE restore_probe")
    print("PASS isolated production ports, secure cookie, billing disabled, PostgreSQL restore and media checksum")


if __name__ == "__main__":
    main()
