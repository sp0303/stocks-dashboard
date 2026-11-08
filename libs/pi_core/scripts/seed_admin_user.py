#!/usr/bin/env python3.13
"""Seed a super-admin user into auth.users.

Usage:
    PYTHONPATH=libs/pi_core:apps/api:apps/workers python3.13 \
        libs/pi_core/scripts/seed_admin_user.py \
        --email admin@sarey.tech --password <your_password>

The script is idempotent: if the email already exists it will print the
existing user's role and exit without modifying anything.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import asyncpg

# ---------------------------------------------------------------------------
# The script lives outside the app package; import directly.
# ---------------------------------------------------------------------------
sys.path.insert(0, "apps/api")

from pi_api.modules.auth.service import hash_password  # noqa: E402

DATABASE_URL = (
    "postgresql://pi_migrator:d1b740b8cd3e01f252141ef0d93098de"
    "@140.245.194.172:5432/portfolio"
)


async def main(email: str, password: str) -> None:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        existing = await conn.fetchrow(
            "SELECT user_id, role FROM auth.users WHERE email = $1", email
        )
        if existing:
            print(
                f"[OK] User {email!r} already exists — "
                f"role={existing['role']}  user_id={existing['user_id']}"
            )
            return

        ph = hash_password(password)
        user = await conn.fetchrow(
            """
            INSERT INTO auth.users (email, password_hash, role)
            VALUES ($1, $2, 'super_admin')
            RETURNING user_id, email, role
            """,
            email,
            ph,
        )
        print(
            f"[CREATED] super_admin user — "
            f"email={user['email']}  user_id={user['user_id']}"
        )
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed a super-admin user")
    parser.add_argument("--email", required=True, help="Admin email address")
    parser.add_argument("--password", required=True, help="Plain-text password (min 8 chars)")
    args = parser.parse_args()

    if len(args.password) < 8:
        print("ERROR: password must be at least 8 characters")
        sys.exit(1)

    asyncio.run(main(args.email, args.password))
