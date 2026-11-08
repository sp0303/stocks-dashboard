"""portfolio.client_analytics: one precomputed analytics payload per client

Expand-only (AGENTS §3.15): creates one new table; nothing existing is altered, so
the previous release keeps working. Written only by portfolio-worker
(pi_workers.analytics_compute, schema ownership §3.5); the API role reads it.

Payload sections (version 1): summary (allocation, concentration, health, beta/alpha,
intraday pool, highlights, manual trades), trades (delivery / intraday analytics),
playbook (by stock), performance (daily net_invested baseline + benchmark P&L, R10).

Revision ID: 0003_client_analytics
Revises: 0002_orb_tables
Create Date: 2026-11-08 12:00:00
"""
from alembic import op

revision = "0003_client_analytics"
down_revision = "0002_orb_tables"
branch_labels = None
depends_on = None

UPGRADE_SQL = """
CREATE TABLE IF NOT EXISTS portfolio.client_analytics (
    client_id      UUID PRIMARY KEY REFERENCES core.clients(client_id),
    as_of          DATE NOT NULL,
    payload        JSONB NOT NULL,
    engine_version TEXT NOT NULL,
    computed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

# Conditional so the migration also runs on a dev database without the roles.
GRANTS_SQL = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pi_api') THEN
        GRANT SELECT ON portfolio.client_analytics TO pi_api;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pi_worker') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON portfolio.client_analytics TO pi_worker;
    END IF;
END $$;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)
    op.execute(GRANTS_SQL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS portfolio.client_analytics;")
