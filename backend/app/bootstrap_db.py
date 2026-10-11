"""Provision DB roles on both existing and fresh volumes; run only as bootstrap owner.

Never run in the API process. This module does not print SQL, passwords or exceptions.
"""

import os
import sys

import psycopg
from psycopg import sql

MIGRATOR = "suni_migrator"
RUNTIME = "suni_runtime"


def provision_roles(admin_url: str, migrator_password: str, runtime_password: str) -> None:
    if min(len(migrator_password), len(runtime_password)) < 32:
        raise ValueError("Database role passwords must be at least 32 characters")
    if migrator_password == runtime_password:
        raise ValueError("Use independent credentials for each role")
    with psycopg.connect(admin_url.replace("postgresql+psycopg://", "postgresql://", 1)) as conn:
        # Serialize provisioning on a reused development database.
        conn.execute("SELECT pg_advisory_xact_lock(731002)")
        for name, password in ((MIGRATOR, migrator_password), (RUNTIME, runtime_password)):
            if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (name,)).fetchone():
                conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(name)))
            # Parameter binding is not supported by PostgreSQL ALTER ROLE PASSWORD.
            # Proper SQL literals are used; do not log these statements.
            conn.execute(
                sql.SQL(
                    "ALTER ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB "
                    "NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT"
                ).format(sql.Identifier(name), sql.Literal(password))
            )
        # Refuse unexpected memberships; NOINHERIT alone does not prevent SET ROLE.
        memberships = conn.execute(
            "SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member "
            "WHERE r.rolname IN (%s, %s)",
            (MIGRATOR, RUNTIME),
        ).fetchone()
        if memberships:
            raise RuntimeError("Unexpected database role membership; requires operator review")
        database = sql.Identifier(conn.info.dbname)
        conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(database))
        for name in (MIGRATOR, RUNTIME):
            role = sql.Identifier(name)
            conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(database, role))
            conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(database, role))
            conn.execute(
                sql.SQL("ALTER ROLE {} IN DATABASE {} SET search_path = public").format(
                    role,
                    database,
                )
            )
        conn.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
        conn.execute(sql.SQL("ALTER SCHEMA public OWNER TO {}").format(sql.Identifier(MIGRATOR)))
        conn.execute(sql.SQL("REVOKE ALL ON SCHEMA public FROM {}").format(sql.Identifier(RUNTIME)))
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(RUNTIME)))
        # Stage 01 baseline table was owned by the bootstrap role. Transfer only that known table.
        if conn.execute("SELECT to_regclass('public.alembic_version')").fetchone()[0]:
            conn.execute(
                sql.SQL("ALTER TABLE public.alembic_version OWNER TO {}").format(
                    sql.Identifier(MIGRATOR),
                )
            )


def main() -> None:
    try:
        provision_roles(
            os.environ["BOOTSTRAP_DATABASE_URL"],
            os.environ["MIGRATOR_PASSWORD"],
            os.environ["RUNTIME_PASSWORD"],
        )
    except Exception:
        print("Database role provisioning failed; credentials and SQL omitted.", file=sys.stderr)
        raise SystemExit(1) from None
    print("Database roles provisioned with separate migration/runtime permissions.")


if __name__ == "__main__":
    main()
