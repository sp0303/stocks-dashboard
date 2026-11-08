"""Soft delete for managers and clients (super-admin / manager-book parity with v1)

Expand-only (AGENTS §3.15): adds a nullable ``deleted_at`` to ``core.managers`` and
``core.clients`` plus partial indexes. Nothing existing changes meaning, so the previous
release keeps working; it simply never sets the column.

A soft delete also sets ``core.managers.is_active = false`` / ``core.clients.status =
'INACTIVE'``, so every query that already filters on those (e.g. the portfolio-worker's
manager_daily roll-up) excludes deleted rows without knowing about ``deleted_at``.
The ledger is append-only (R13): trades of a deleted client are never removed.

Revision ID: 0004_admin_parity
Revises: 0003_client_analytics
Create Date: 2026-11-08 12:00:00
"""

from alembic import op

revision = "0004_admin_parity"
down_revision = "0003_client_analytics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE core.managers ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE core.clients ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS managers_live_idx ON core.managers (name) "
        "WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS clients_live_manager_idx ON core.clients (manager_id) "
        "WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS core.clients_live_manager_idx")
    op.execute("DROP INDEX IF EXISTS core.managers_live_idx")
    op.execute("ALTER TABLE core.clients DROP COLUMN IF EXISTS deleted_at")
    op.execute("ALTER TABLE core.managers DROP COLUMN IF EXISTS deleted_at")
