"""orb.* tables mirrored from v1 Mongo (universe, signals, health, jobs, journal)

Expand-only: creates five new tables in the existing (empty) `orb` schema. Nothing
existing is altered, so the previous release keeps working (AGENTS §3.15).

Until cutover these tables are filled by the read-only v1-Mongo sync
(pi_workers.orb_feed / scripts/sync_v1_orb_to_v2.py). `legacy_id` is the v1 `_id`
as text and is the idempotency key; `source_hash` lets a re-sync skip unchanged rows.
Prices are integer paise, as in v1 (lossless); the API converts to rupees.
Candles are NOT here: they live in market.candles_1m / market.eod_prices.

Revision ID: 0002_orb_tables
Revises: 0001_initial_schema
Create Date: 2026-10-04 12:00:00
"""
from alembic import op

revision = "0002_orb_tables"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

_COMMON = """
    id           BIGSERIAL PRIMARY KEY,
    legacy_id    TEXT NOT NULL UNIQUE,
    source       TEXT NOT NULL DEFAULT 'v1_mongo',
    source_hash  TEXT NOT NULL,
    synced_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    extra        JSONB NOT NULL DEFAULT '{}'::jsonb
"""

UPGRADE_SQL = f"""
CREATE SCHEMA IF NOT EXISTS orb;

CREATE TABLE IF NOT EXISTS orb.universe (
    {_COMMON},
    trade_date       DATE NOT NULL,
    size             INTEGER,
    min_turnover_cr  NUMERIC(18,4),
    pool             JSONB,
    members          JSONB NOT NULL DEFAULT '[]'::jsonb,
    ranked           JSONB
);
CREATE INDEX IF NOT EXISTS ix_orb_universe_date ON orb.universe (trade_date DESC);

CREATE TABLE IF NOT EXISTS orb.signals (
    {_COMMON},
    trade_date   DATE NOT NULL,
    kind         TEXT NOT NULL,
    sym          TEXT,
    minute       INTEGER,
    side         SMALLINT,
    entry_paise  BIGINT,
    stop_paise   BIGINT,
    t1_paise     BIGINT,
    t2_paise     BIGINT,
    qty          INTEGER,
    risk_paise   BIGINT,
    candidates   INTEGER,
    passed       INTEGER,
    shortlist    JSONB,
    screen_rows  JSONB,
    trace        JSONB,
    config       TEXT,
    at           TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_orb_signals_date_kind ON orb.signals (trade_date DESC, kind);

CREATE TABLE IF NOT EXISTS orb.health (
    {_COMMON},
    trade_date        DATE,
    kind              TEXT NOT NULL,
    agree_pct         NUMERIC(9,3),
    passes_exit_test  BOOLEAN,
    symbols           INTEGER,
    minutes_compared  INTEGER,
    minutes_matched   INTEGER,
    at                TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_orb_health_date ON orb.health (trade_date DESC, kind);

CREATE TABLE IF NOT EXISTS orb.jobs (
    {_COMMON},
    trade_date  DATE,
    job         TEXT,
    ok          BOOLEAN,
    minute      INTEGER,
    detail      TEXT,
    seconds     NUMERIC(12,2),
    owner       TEXT,
    at          TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_orb_jobs_date ON orb.jobs (trade_date DESC, job);

CREATE TABLE IF NOT EXISTS orb.journal (
    {_COMMON},
    trade_date   DATE NOT NULL,
    sym          TEXT NOT NULL,
    reason       TEXT,
    side         SMALLINT,
    minute       INTEGER,
    qty          INTEGER,
    price_paise  BIGINT,
    entry_paise  BIGINT,
    stop_paise   BIGINT,
    r            NUMERIC(12,3),
    config       TEXT,
    at           TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_orb_journal_date ON orb.journal (trade_date DESC, minute);
"""

# Grants are conditional so the migration also runs on a dev database without the roles.
GRANTS_SQL = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pi_api') THEN
        GRANT USAGE ON SCHEMA orb TO pi_api;
        GRANT SELECT ON ALL TABLES IN SCHEMA orb TO pi_api;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pi_worker') THEN
        GRANT USAGE ON SCHEMA orb TO pi_worker;
        GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA orb TO pi_worker;
        GRANT USAGE ON ALL SEQUENCES IN SCHEMA orb TO pi_worker;
    END IF;
END $$;
"""

TABLES = ("journal", "jobs", "health", "signals", "universe")


def upgrade() -> None:
    op.execute(UPGRADE_SQL)
    op.execute(GRANTS_SQL)


def downgrade() -> None:
    for t in TABLES:
        op.execute(f"DROP TABLE IF EXISTS orb.{t};")
