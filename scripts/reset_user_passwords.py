#!/usr/bin/env python
"""Reset v2 login passwords to fresh random temporary ones.

Run by the OWNER on the box, never by an agent: the new passwords are printed to this
terminal only (AGENTS §9 — credentials never pass through an agent transcript).
Passwords are stored as argon2id hashes and can't be read back; resetting is the only way
to hand someone a working password. Existing sessions of a reset user are revoked.

    sudo pi-run scripts/reset_user_passwords.py            # list logins, change nothing
    sudo pi-run scripts/reset_user_passwords.py --all      # reset every active login
    sudo pi-run scripts/reset_user_passwords.py --email a@b.com [--email ...]

Env: PG_DSN (or DATABASE_URL) for a role that can UPDATE auth.users.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import string
import sys

import asyncpg

from pi_api.modules.auth.service import hash_password

_ALPHABET = string.ascii_letters + string.digits


def temp_password(n: int = 14) -> str:
    """Random temporary password: letters + digits, with at least one of each."""
    while True:
        pw = "".join(secrets.choice(_ALPHABET) for _ in range(n))
        if any(c.isdigit() for c in pw) and any(c.isalpha() for c in pw):
            return pw


async def run(dsn: str, emails: list[str], reset_all: bool) -> int:
    conn = await asyncpg.connect(dsn, timeout=15)
    try:
        users = await conn.fetch(
            "SELECT user_id, email::text AS email, role, is_active "
            "FROM auth.users ORDER BY role, email"
        )
        if not emails and not reset_all:
            print(f"{'ROLE':12} {'ACTIVE':6} EMAIL")
            for u in users:
                print(f"{u['role']:12} {str(u['is_active']):6} {u['email']}")
            print("\nNothing changed. Use --all or --email to reset.")
            return 0
        wanted = {e.lower() for e in emails}
        targets = [
            u for u in users
            if (reset_all and u["is_active"]) or u["email"].lower() in wanted
        ]
        missing = wanted - {u["email"].lower() for u in targets}
        out = []
        async with conn.transaction():
            for u in targets:
                pw = temp_password()
                await conn.execute(
                    "UPDATE auth.users SET password_hash = $1 WHERE user_id = $2",
                    hash_password(pw), u["user_id"],
                )
                await conn.execute(
                    "UPDATE auth.refresh_tokens SET revoked = true WHERE user_id = $1",
                    u["user_id"],
                )
                out.append((u["role"], u["email"], pw))
        print("\n=== NEW TEMPORARY PASSWORDS (shown once; share privately) ===")
        for role, email, pw in out:
            print(f"{role:12} {email:36} {pw}")
        for e in sorted(missing):
            print(f"not found: {e}", file=sys.stderr)
        return 1 if missing else 0
    finally:
        await conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--email", action="append", default=[], help="reset this login (repeatable)")
    ap.add_argument("--all", action="store_true", help="reset every active login")
    a = ap.parse_args()
    dsn = os.environ.get("PG_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        print("error: set PG_DSN or DATABASE_URL", file=sys.stderr)
        return 2
    return asyncio.run(run(dsn, a.email, a.all))


if __name__ == "__main__":
    sys.exit(main())
