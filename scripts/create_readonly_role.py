"""Create the read-only database role the ask agent's SQL tool connects as.

    uv run python scripts/create_readonly_role.py            # create it, write the URL to .env
    uv run python scripts/create_readonly_role.py --rotate   # new password for an existing role

Connects with DATABASE_URL (the owner role), creates `labellens_readonly` with LOGIN, a
generated password and nothing else, and writes DATABASE_URL_READONLY to .env (same host and
database). Neither the password nor the URL is printed.

Roles made in Neon's console join neon_superuser, which is far too much for a tool that runs
model-written SQL, so this one is made with SQL. The serving loader grants it USAGE on
`serving` and SELECT on the public tables only, after every swap. The role also defaults to
read-only transactions with a 3-second statement timeout, in case a connection skips them.
"""

from __future__ import annotations

import argparse
import re
import secrets
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
ENV_KEY = "DATABASE_URL_READONLY"
# Kept equal to pipeline.load.serving.READONLY_ROLE (a test checks).
ROLE = "labellens_readonly"


def role_url(admin_url: str, role: str, password: str) -> str:
    """The admin URL with the role's credentials in place of the owner's."""
    parts = urlsplit(admin_url)
    host = parts.netloc.rsplit("@", 1)[-1]
    netloc = f"{quote(role, safe='')}:{quote(password, safe='')}@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def create_role(
    admin_url: str, role: str = ROLE, *, rotate: bool = False, password: str | None = None
) -> str:
    """Create (or, with rotate, re-password) the role. Returns its connection URL.

    The password is random unless given. Tests give a fixed local one: roles belong to the
    whole Postgres cluster, so two test runs at once would otherwise re-password each other.
    """
    password = password or secrets.token_urlsafe(24)
    with psycopg.connect(admin_url, autocommit=True, prepare_threshold=None) as pg:
        exists = pg.execute("select 1 from pg_roles where rolname = %s", [role]).fetchone()
        name = sql.Identifier(role)
        if exists and not rotate:
            raise SystemExit(f"Role {role} exists already. Use --rotate for a new password.")
        verb = sql.SQL("alter") if exists else sql.SQL("create")
        pg.execute(
            sql.SQL(
                "{} role {} login password {} nosuperuser nocreatedb nocreaterole noinherit"
            ).format(verb, name, sql.Literal(password))
        )
        pg.execute(sql.SQL("alter role {} set default_transaction_read_only = on").format(name))
        pg.execute(sql.SQL("alter role {} set statement_timeout = '3s'").format(name))
    return role_url(admin_url, role, password)


def write_env(path: Path, key: str, value: str, *, replace: bool) -> None:
    """Set key=value in a .env file: fill an empty line, replace one (if allowed), or append."""
    lines = path.read_text("utf-8").splitlines() if path.exists() else []
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=(.*)$")
    for i, line in enumerate(lines):
        match = pattern.match(line)
        if match:
            if match.group(1).strip() and not replace:
                raise SystemExit(
                    f"{key} is already set in {path.name}. Use --rotate to replace it."
                )
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", "utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create the read-only role for the ask agent.")
    parser.add_argument("--rotate", action="store_true", help="new password for an existing role")
    parser.add_argument("--env-file", type=Path, default=ENV_FILE)
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT))
    from api.app.config import get_settings

    secret = get_settings().database_url
    if not secret:
        print("DATABASE_URL is not set in .env.", file=sys.stderr)
        return 1
    url = create_role(secret.get_secret_value(), rotate=args.rotate)
    write_env(args.env_file, ENV_KEY, url, replace=args.rotate)
    print(f"Role {ROLE} is ready and {ENV_KEY} is in {args.env_file.name} (not printed).")
    print("Next: reload the serving tables so it gets its grants:")
    print("  uv run python -m pipeline.load.serving")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
