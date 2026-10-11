"""Local Docker operations. Never connects to SSH or changes Cloudflare.

Encrypted backups include PostgreSQL and private media in one restic snapshot.
Restore is deliberately restricted to a new database/container in the test project.
"""
import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESTIC = "restic/restic@sha256:4cf4a61ef9786f4de53e9de8c8f5c040f33830eb0a10bf3d614410ee2fcb6120"
PROFILES = {
    "local": ["-p", "suni", "-f", "compose.yaml"],
    "test": ["--env-file", "test-results/stage12.env", "-p", "suni-production-check",
             "-f", "compose.yaml", "-f", "compose.production.yaml"],
    "production": ["--env-file", ".env.production", "-p", "suni-production",
                   "-f", "compose.yaml", "-f", "compose.production.yaml"],
}
SERVICES = {"api", "web", "postgres", "redis", "worker", "beat"}
WRITERS = ["web", "api", "beat", "worker"]


def host_user():
    # Linux bind mounts preserve uid/mode; avoid root-owned backup files.
    return ["--user", f"{os.getuid()}:{os.getgid()}"] if os.name == "posix" else []


def execute(args, *, output=None, data=None):
    result = subprocess.run(args, cwd=ROOT, input=data, stdout=output or subprocess.PIPE,
                            stderr=subprocess.PIPE, check=False)
    if result.returncode:
        # Don't echo commands, env, stderr, or arbitrary server data into logs.
        raise RuntimeError(f"Operation failed ({args[0]}, exit {result.returncode})")
    return result.stdout


def compose(profile, *args, **kwargs):
    return execute(["docker", "compose", *PROFILES[profile], *args], **kwargs)


def rows(profile):
    raw = compose(profile, "ps", "--all", "--format", "json").decode().strip()
    if not raw:
        return []
    return json.loads(raw) if raw.startswith("[") else [json.loads(line) for line in raw.splitlines()]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@contextmanager
def maintenance(profile):
    directory = ROOT / "backups"
    directory.mkdir(mode=0o700, exist_ok=True)
    lock = directory / f".{profile}.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        yield
    finally:
        lock.unlink()


def restic(repository, password, *args, mounts=()):
    options = ["docker", "run", "--rm", "--network", "none", "--read-only",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
               "--tmpfs", "/tmp:size=128m", "--mount",
               f"type=bind,source={repository},target=/repository",
               "--mount", f"type=bind,source={password},target=/password,readonly"]
    for source, target, readonly in mounts:
        options += ["--mount", f"type=bind,source={source},target={target}" + (",readonly" if readonly else "")]
    return execute(options + host_user() + [RESTIC, "--repo", "/repository", "--password-file", "/password",
                              "--no-cache", *args])


def paths(directory):
    directory = Path(directory).resolve()
    repository, password = directory / "repository", directory / "password"
    if not (repository / "config").is_file() or not password.is_file():
        raise RuntimeError("Backup directory is not initialized")
    return directory, repository, password


def initialize(directory):
    directory = Path(directory).resolve()
    # Never overwrite an existing directory/password/repository.
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    repository = directory / "repository"
    repository.mkdir(mode=0o700)
    password = directory / "password"
    fd = os.open(password, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(secrets.token_hex(32))
    restic(repository, password, "init")
    print("Encrypted local repository initialized. Keep a separate secure copy of its password file.")


def backup(profile, directory):
    directory, repository, password = paths(directory)
    with maintenance(profile):
        active = {row["Service"] for row in rows(profile) if row["State"] == "running"}
        if not SERVICES.issubset(active):
            raise RuntimeError("All application services must be running before backup")
        restic(repository, password, "cat", "config")
        with tempfile.TemporaryDirectory(prefix="suni-backup-", dir=directory) as staging:
            stage = Path(staging)
            try:
                compose(profile, "stop", "-t", "600", *WRITERS)
                # No asynchronous writer may survive the quiescence boundary.
                if any(row["Service"] in WRITERS and row["State"] == "running" for row in rows(profile)):
                    raise RuntimeError("A writer is still running")
                with (stage / "database.dump").open("wb") as output:
                    compose(profile, "exec", "-T", "postgres", "sh", "-c",
                            'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc', output=output)
                with (stage / "media.tar").open("wb") as output:
                    compose(profile, "run", "--rm", "--no-deps", "-T", "api", "python", "-c",
                            'import sys,tarfile; t=tarfile.open(fileobj=sys.stdout.buffer,mode="w|"); '
                            't.add("/var/lib/suni-media",arcname="media"); t.close()', output=output)
                manifest = {name: digest(stage / name) for name in ["database.dump", "media.tar"]}
                (stage / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
                raw = restic(repository, password, "backup", "--json", "--tag", profile, "/snapshot",
                             mounts=[(stage, "/snapshot", True)])
                summary = [json.loads(line) for line in raw.splitlines()
                           if json.loads(line).get("message_type") == "summary"][-1]
                restic(repository, password, "check", "--read-data")
                state = {"snapshot": summary["snapshot_id"], "completed_at": time.time(), "profile": profile}
                temporary = directory / "state.tmp"
                temporary.write_text(json.dumps(state), encoding="utf-8")
                temporary.replace(directory / "state.json")
            finally:
                compose(profile, "up", "--no-deps", "-d", "--wait", "--wait-timeout", "180", *WRITERS)
    print(json.dumps({"backup": "ok", **state}))
    return state


def verify_manifest(directory):
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if set(manifest) != {"database.dump", "media.tar"}:
        raise RuntimeError("Invalid backup manifest")
    for name, expected in manifest.items():
        if not isinstance(expected, str) or digest(directory / name) != expected:
            raise RuntimeError("Backup checksum mismatch")


def restore_test(directory):
    directory, repository, password = paths(directory)
    state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    if state["profile"] != "test":
        raise RuntimeError("Restore drill only accepts snapshots of the isolated test project")
    with maintenance("test"), tempfile.TemporaryDirectory(prefix="suni-restore-", dir=directory) as staging:
        stage = Path(staging)
        restic(repository, password, "restore", state["snapshot"], "--target", "/restore",
               mounts=[(stage, "/restore", False)])
        snapshot = stage / "snapshot"
        verify_manifest(snapshot)
        database = "suni_restore_" + uuid.uuid4().hex
        def sql(query):
            return compose("test", "exec", "-T", "postgres", "psql", "-U", "suni", "-d", database,
                           "-At", "-v", "ON_ERROR_STOP=1", "-c", query).decode().strip()
        # Unique new database: never overwrite or downgrade any existing database.
        compose("test", "exec", "-T", "postgres", "createdb", "-U", "suni", database)
        try:
            with (snapshot / "database.dump").open("rb") as source:
                process = subprocess.run(["docker", "compose", *PROFILES["test"], "exec", "-T", "postgres",
                                          "pg_restore", "-U", "suni", "-d", database, "--no-owner",
                                          "--no-acl", "--exit-on-error"], cwd=ROOT, stdin=source,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False)
            if process.returncode:
                raise RuntimeError("Database restore failed")
            if sql("SELECT version_num FROM alembic_version") != "0010_content_access":
                raise RuntimeError("Unexpected restored schema")
            if sql("SELECT encode(payload,'hex') FROM restore_probe") != "deadbeef00ff":
                raise RuntimeError("Binary fixture restore failed")
            # Extract only in a fresh container /tmp. Never mount the live media volume.
            cid = compose("test", "ps", "-q", "api").decode().strip()
            image = execute(["docker", "inspect", "--format", "{{.Image}}", cid]).decode().strip()
            execute(["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
                     "--security-opt", "no-new-privileges", "--tmpfs", "/tmp:size=128m,mode=1777",
                     "--mount", f"type=bind,source={snapshot},target=/snapshot,readonly", *host_user(), image, "python", "-c",
                     ('import tarfile,pathlib; t=tarfile.open("/snapshot/media.tar"); '
                     't.extractall("/tmp/restore",filter="data"); '
                     'assert pathlib.Path("/tmp/restore/media/restore-probe").read_bytes()==bytes(range(256))')])
        finally:
            compose("test", "exec", "-T", "postgres", "dropdb", "-U", "suni", database)
    print("PASS encrypted snapshot, PostgreSQL binary fixture and isolated media extraction")


def assess(service_rows, free_fraction, backup_state, current_time):
    findings = []
    by_name = {row["Service"]: row for row in service_rows}
    for name in sorted(SERVICES):
        row = by_name.get(name)
        if not row or row.get("State") != "running" or row.get("Health") in {"unhealthy", "starting"}:
            findings.append(f"service_unavailable:{name}")
    if free_fraction < .2:
        findings.append("disk_free_below_20_percent")
    if not backup_state or current_time - backup_state.get("completed_at", 0) > 26 * 3600:
        findings.append("backup_missing_or_older_than_26h")
    return findings


def status(profile, directory):
    state_path = Path(directory) / "state.json"
    state = json.loads(state_path.read_text()) if state_path.is_file() else None
    if state and state.get("profile") != profile:
        state = None
    disk = shutil.disk_usage(ROOT)
    findings = assess(rows(profile), disk.free / disk.total, state, time.time())
    print(json.dumps({"status": "attention" if findings else "ok", "findings": findings}))
    return 1 if findings else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "backup", "restore-test", "status"])
    parser.add_argument("--profile", choices=PROFILES, default="local")
    parser.add_argument("--directory", type=Path, default=ROOT / "backups" / "local")
    args = parser.parse_args()
    try:
        if args.action == "init":
            initialize(args.directory)
        elif args.action == "backup":
            backup(args.profile, args.directory)
        elif args.action == "restore-test":
            restore_test(args.directory)
        else:
            return status(args.profile, args.directory)
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        # Fixed error type only: arbitrary paths/remote diagnostics may contain secrets.
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
