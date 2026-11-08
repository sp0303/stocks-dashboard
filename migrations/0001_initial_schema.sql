-- Portfolio Intelligence v2 — Initial Schema (Pure PostgreSQL 16, no TimescaleDB)
-- Generated from docs/v2/architecture/LLD-database.md

CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS ledger;
CREATE SCHEMA IF NOT EXISTS market;
CREATE SCHEMA IF NOT EXISTS portfolio;
CREATE SCHEMA IF NOT EXISTS research;
CREATE SCHEMA IF NOT EXISTS orb;
CREATE SCHEMA IF NOT EXISTS ops;

-- 4.1 core and auth
CREATE TABLE IF NOT EXISTS core.managers (
    manager_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    legacy_id   TEXT UNIQUE,
    name        TEXT   NOT NULL,
    firm        TEXT,
    email       CITEXT NOT NULL UNIQUE,
    is_active   BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.clients (
    client_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    legacy_id   TEXT UNIQUE,
    manager_id  UUID NOT NULL REFERENCES core.managers(manager_id),
    name        TEXT NOT NULL,
    client_code TEXT,
    broker      TEXT CHECK (broker IN ('ZERODHA','UPSTOX','ANGEL','OTHER')),
    status      TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS clients_code_per_manager ON core.clients (manager_id, client_code) WHERE client_code IS NOT NULL;

CREATE TABLE IF NOT EXISTS auth.users (
    user_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         CITEXT NOT NULL UNIQUE,
    password_hash TEXT   NOT NULL,
    role          TEXT   NOT NULL CHECK (role IN ('super_admin','manager','client')),
    manager_id    UUID REFERENCES core.managers(manager_id),
    client_id     UUID REFERENCES core.clients(client_id),
    is_active     BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ,
    CHECK ((role = 'manager' AND manager_id IS NOT NULL) OR
           (role = 'client'  AND client_id  IS NOT NULL) OR role = 'super_admin')
);

CREATE TABLE IF NOT EXISTS auth.refresh_tokens (
    token_hash BYTEA PRIMARY KEY,
    user_id    UUID NOT NULL REFERENCES auth.users(user_id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked    BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS auth.audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID,
    action TEXT NOT NULL,
    entity TEXT,
    entity_id TEXT,
    meta JSONB,
    at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS audit_log_at_idx ON auth.audit_log (at DESC);

-- 4.2 ledger
CREATE TABLE IF NOT EXISTS ledger.uploads (
    upload_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    legacy_id       TEXT UNIQUE,
    client_id       UUID NOT NULL REFERENCES core.clients(client_id),
    version         INT  NOT NULL,
    file_name       TEXT NOT NULL,
    file_sha256     BYTEA NOT NULL,
    raw_object_key  TEXT,
    broker_format   TEXT NOT NULL CHECK (broker_format IN ('ZERODHA','UPSTOX','OTHER')),
    date_from       DATE,
    date_to         DATE,
    rows_total      INT NOT NULL,
    rows_imported   INT NOT NULL,
    rows_duplicate  INT NOT NULL,
    rows_rejected   INT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('QUEUED','PROCESSING','IMPORTED','PARTIAL','FAILED')),
    uploaded_by     UUID REFERENCES auth.users(user_id),
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (client_id, file_sha256)
);

CREATE TABLE IF NOT EXISTS ledger.upload_rejects (
    upload_id UUID NOT NULL REFERENCES ledger.uploads(upload_id) ON DELETE CASCADE,
    row_no INT NOT NULL,
    reason TEXT NOT NULL,
    raw JSONB NOT NULL,
    PRIMARY KEY (upload_id, row_no)
);

CREATE TABLE IF NOT EXISTS ledger.trades (
    trade_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    legacy_id       TEXT UNIQUE,
    client_id       UUID NOT NULL REFERENCES core.clients(client_id),
    fingerprint     TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    isin            TEXT,
    trade_date      DATE NOT NULL,
    exchange        TEXT NOT NULL CHECK (exchange IN ('NSE','BSE')),
    segment         TEXT NOT NULL DEFAULT 'EQ',
    series          TEXT,
    trade_type      TEXT NOT NULL CHECK (trade_type IN ('buy','sell')),
    auction         BOOLEAN NOT NULL DEFAULT false,
    quantity        NUMERIC(18,6) NOT NULL CHECK (quantity > 0),
    price           NUMERIC(18,4) NOT NULL CHECK (price >= 0),
    trade_value     NUMERIC(18,4) GENERATED ALWAYS AS (quantity * price) STORED,
    broker_trade_id TEXT,
    broker_order_id TEXT,
    executed_at     TIMESTAMPTZ,
    charges         NUMERIC(18,4),
    charges_known   BOOLEAN NOT NULL DEFAULT false,
    source          TEXT NOT NULL CHECK (source IN ('upload','manual','kite','angel')),
    upload_id       UUID REFERENCES ledger.uploads(upload_id),
    note            TEXT,
    extra           JSONB NOT NULL DEFAULT '{}',
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (client_id, fingerprint),
    CHECK (price > 0 OR source = 'manual')
);
CREATE INDEX IF NOT EXISTS trades_client_date   ON ledger.trades (client_id, trade_date, trade_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS trades_client_symbol ON ledger.trades (client_id, symbol, trade_date)  WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS ledger.dividends (
    dividend_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id UUID NOT NULL REFERENCES core.clients(client_id),
    symbol TEXT NOT NULL,
    ex_date DATE NOT NULL,
    amount_per_share NUMERIC(18,4) NOT NULL,
    quantity NUMERIC(18,6) NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('manual','nse'))
);

CREATE TABLE IF NOT EXISTS ledger.corporate_actions (
    action_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    isin TEXT,
    symbol TEXT NOT NULL,
    ex_date DATE NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('SPLIT','BONUS','DIVIDEND','DEMERGER','MERGER','BUYBACK','RIGHTS','DELISTING','OTHER')),
    qty_multiplier NUMERIC(18,8),
    amount_per_share NUMERIC(18,4),
    subject TEXT,
    source TEXT NOT NULL DEFAULT 'NSE',
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ca_isin_idx ON ledger.corporate_actions (isin);
CREATE INDEX IF NOT EXISTS ca_symbol_ex_date_idx ON ledger.corporate_actions (symbol, ex_date);

CREATE TABLE IF NOT EXISTS ledger.cost_basis_adjustments (
    adjustment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id UUID NOT NULL REFERENCES core.clients(client_id),
    symbol TEXT NOT NULL,
    quantity NUMERIC(18,6) NOT NULL,
    unit_cost NUMERIC(18,4) NOT NULL,
    acquired_on DATE,
    reason TEXT NOT NULL,
    created_by UUID REFERENCES auth.users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 4.3 market
CREATE TABLE IF NOT EXISTS market.securities (
    security_id  INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    symbol       TEXT NOT NULL,
    exchange     TEXT NOT NULL CHECK (exchange IN ('NSE','BSE')),
    isin         TEXT,
    name         TEXT,
    sector       TEXT,
    industry     TEXT,
    asset_class  TEXT,
    cap          TEXT,
    angel_token  TEXT,
    is_active    BOOLEAN NOT NULL DEFAULT true,
    UNIQUE (symbol, exchange)
);
CREATE INDEX IF NOT EXISTS securities_isin_idx ON market.securities (isin);
CREATE INDEX IF NOT EXISTS securities_symbol_trgm ON market.securities USING gin (symbol gin_trgm_ops);

CREATE TABLE IF NOT EXISTS market.symbol_aliases (
    old_symbol TEXT NOT NULL,
    new_symbol TEXT NOT NULL,
    isin TEXT NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE,
    PRIMARY KEY (old_symbol, valid_from)
);

CREATE TABLE IF NOT EXISTS market.trading_calendar (
    cal_date DATE PRIMARY KEY,
    is_open BOOLEAN NOT NULL,
    session_open TIME,
    session_close TIME,
    note TEXT
);

CREATE TABLE IF NOT EXISTS market.eod_prices (
    security_id INT NOT NULL REFERENCES market.securities(security_id),
    price_date DATE NOT NULL,
    open NUMERIC(18,4),
    high NUMERIC(18,4),
    low NUMERIC(18,4),
    close NUMERIC(18,4) NOT NULL CHECK (close > 0),
    volume BIGINT,
    source TEXT NOT NULL,
    adjusted BOOLEAN NOT NULL DEFAULT false,
    ingest_id BIGINT,
    PRIMARY KEY (security_id, price_date)
);
CREATE INDEX IF NOT EXISTS eod_prices_date_idx ON market.eod_prices (price_date DESC);

CREATE TABLE IF NOT EXISTS market.candles_1m (
    security_id INT NOT NULL REFERENCES market.securities(security_id),
    ts TIMESTAMPTZ NOT NULL,
    o INT NOT NULL,
    h INT NOT NULL,
    l INT NOT NULL,
    c INT NOT NULL,
    v BIGINT NOT NULL,
    synthetic BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (security_id, ts)
);
CREATE INDEX IF NOT EXISTS candles_1m_sec_ts_idx ON market.candles_1m (security_id, ts DESC);

CREATE TABLE IF NOT EXISTS market.benchmarks (
    benchmark_id SMALLINT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    provider_symbol TEXT NOT NULL,
    is_tri BOOLEAN NOT NULL DEFAULT false,
    is_active BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS market.benchmark_values (
    benchmark_id SMALLINT NOT NULL REFERENCES market.benchmarks(benchmark_id),
    value_date DATE NOT NULL,
    value NUMERIC(18,4) NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (benchmark_id, value_date)
);

CREATE OR REPLACE VIEW market.benchmark_health AS
SELECT b.code, max(v.value_date) AS last_date,
       (SELECT max(cal_date) FROM market.trading_calendar WHERE is_open AND cal_date <= current_date) AS last_session,
       (SELECT count(*) FROM market.trading_calendar c WHERE c.is_open AND c.cal_date > max(v.value_date) AND c.cal_date <= current_date) AS sessions_behind
FROM market.benchmarks b LEFT JOIN market.benchmark_values v USING (benchmark_id) WHERE b.is_active GROUP BY b.code;

-- 4.4 portfolio
CREATE TABLE IF NOT EXISTS portfolio.client_daily (
    client_id UUID NOT NULL REFERENCES core.clients(client_id),
    as_of DATE NOT NULL,
    market_value NUMERIC(18,2) NOT NULL,
    open_cost    NUMERIC(18,2) NOT NULL,
    net_invested NUMERIC(18,2) NOT NULL,
    realized_pnl NUMERIC(18,2) NOT NULL,
    twr_base     NUMERIC(18,2),
    day_return   DOUBLE PRECISION,
    nav          DOUBLE PRECISION NOT NULL,
    unpriced_cost NUMERIC(18,2) NOT NULL DEFAULT 0,
    flags SMALLINT NOT NULL DEFAULT 0,
    engine_version TEXT NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (client_id, as_of)
);

CREATE TABLE IF NOT EXISTS portfolio.client_benchmark_daily (
    client_id UUID NOT NULL REFERENCES core.clients(client_id),
    benchmark_id SMALLINT NOT NULL REFERENCES market.benchmarks(benchmark_id),
    as_of DATE NOT NULL,
    units NUMERIC(24,8) NOT NULL,
    value NUMERIC(18,2) NOT NULL,
    pnl NUMERIC(18,2) NOT NULL,
    PRIMARY KEY (client_id, benchmark_id, as_of)
);

CREATE TABLE IF NOT EXISTS portfolio.positions_latest (
    client_id UUID NOT NULL REFERENCES core.clients(client_id),
    security_id INT NOT NULL REFERENCES market.securities(security_id),
    quantity NUMERIC(18,6) NOT NULL,
    avg_cost NUMERIC(18,4) NOT NULL,
    invested NUMERIC(18,2) NOT NULL,
    entry_date DATE,
    applied_actions JSONB NOT NULL DEFAULT '[]',
    PRIMARY KEY (client_id, security_id)
);

CREATE TABLE IF NOT EXISTS portfolio.client_overview (
    client_id UUID PRIMARY KEY REFERENCES core.clients(client_id),
    as_of DATE NOT NULL,
    payload JSONB NOT NULL,
    engine_version TEXT NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS portfolio.client_metrics (
    client_id UUID PRIMARY KEY REFERENCES core.clients(client_id),
    as_of DATE NOT NULL,
    obs INT NOT NULL,
    payload JSONB NOT NULL,
    engine_version TEXT NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS portfolio.round_trips (
    client_id UUID NOT NULL REFERENCES core.clients(client_id),
    symbol TEXT NOT NULL,
    buy_date DATE NOT NULL,
    sell_date DATE NOT NULL,
    quantity NUMERIC(18,6) NOT NULL,
    buy_price NUMERIC(18,4) NOT NULL,
    sell_price NUMERIC(18,4) NOT NULL,
    pnl NUMERIC(18,2) NOT NULL,
    days INT NOT NULL,
    PRIMARY KEY (client_id, symbol, buy_date, sell_date, quantity)
);

CREATE TABLE IF NOT EXISTS portfolio.trade_analytics (
    client_id UUID PRIMARY KEY REFERENCES core.clients(client_id),
    as_of DATE NOT NULL,
    payload JSONB NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS portfolio.manager_daily (
    manager_id UUID NOT NULL REFERENCES core.managers(manager_id),
    as_of DATE NOT NULL,
    market_value NUMERIC(18,2) NOT NULL,
    open_cost NUMERIC(18,2) NOT NULL,
    net_invested NUMERIC(18,2) NOT NULL,
    realized_pnl NUMERIC(18,2) NOT NULL,
    pnl NUMERIC(18,2) NOT NULL,
    PRIMARY KEY (manager_id, as_of)
);

CREATE TABLE IF NOT EXISTS portfolio.manager_benchmark_daily (
    manager_id UUID NOT NULL REFERENCES core.managers(manager_id),
    benchmark_id SMALLINT NOT NULL REFERENCES market.benchmarks(benchmark_id),
    as_of DATE NOT NULL,
    pnl NUMERIC(18,2) NOT NULL,
    PRIMARY KEY (manager_id, benchmark_id, as_of)
);

-- 4.5 research and orb
CREATE TABLE IF NOT EXISTS research.watchlists (
    watchlist_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_type TEXT NOT NULL CHECK (owner_type IN ('MANAGER','CLIENT')),
    owner_id UUID NOT NULL,
    name TEXT NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS research.watchlist_entries (
    watchlist_id UUID NOT NULL REFERENCES research.watchlists(watchlist_id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    added_date DATE NOT NULL,
    added_price NUMERIC(18,4),
    why TEXT,
    remarks TEXT,
    risks TEXT,
    sector TEXT,
    alert_price NUMERIC(18,4),
    alert_date DATE,
    PRIMARY KEY (watchlist_id, symbol)
);

CREATE TABLE IF NOT EXISTS research.board_items (
    item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_type TEXT NOT NULL,
    owner_id UUID NOT NULL,
    symbol TEXT NOT NULL,
    lane TEXT NOT NULL CHECK (lane IN ('watching','holding','exit')),
    entry_price NUMERIC(18,4),
    exit_price NUMERIC(18,4),
    why TEXT,
    colour TEXT,
    sort_order INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS research.tags (
    tag_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id UUID NOT NULL REFERENCES core.clients(client_id),
    name TEXT NOT NULL,
    colour TEXT,
    description TEXT,
    UNIQUE (client_id, name)
);

CREATE TABLE IF NOT EXISTS research.trade_tags (
    client_id UUID NOT NULL REFERENCES core.clients(client_id),
    trade_id BIGINT NOT NULL REFERENCES ledger.trades(trade_id) ON DELETE CASCADE,
    tag_id BIGINT NOT NULL REFERENCES research.tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (trade_id, tag_id)
);

CREATE TABLE IF NOT EXISTS research.trade_notes (
    client_id UUID NOT NULL REFERENCES core.clients(client_id),
    trade_id BIGINT NOT NULL REFERENCES ledger.trades(trade_id) ON DELETE CASCADE PRIMARY KEY,
    note TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS research.stock_theses (
    client_id UUID NOT NULL REFERENCES core.clients(client_id),
    symbol TEXT NOT NULL,
    thesis JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (client_id, symbol)
);

CREATE TABLE IF NOT EXISTS research.screener_snapshots (
    as_of DATE NOT NULL,
    model TEXT NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (as_of, model)
);

-- 4.6 ops
CREATE TABLE IF NOT EXISTS ops.job_runs (
    run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('RUNNING','OK','FAILED','SKIPPED')),
    rows_in BIGINT,
    rows_out BIGINT,
    error TEXT,
    meta JSONB
);
CREATE INDEX IF NOT EXISTS job_runs_job_started_idx ON ops.job_runs (job, started_at DESC);

CREATE TABLE IF NOT EXISTS ops.ingest_log (
    ingest_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source TEXT NOT NULL,
    business_date DATE,
    raw_sha256 BYTEA,
    object_key TEXT,
    rows_in INT,
    rows_loaded INT,
    rows_rejected INT,
    retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, raw_sha256)
);

CREATE TABLE IF NOT EXISTS ops.dq_issues (
    issue_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    check_name TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('INFO','WARN','BLOCK')),
    entity_key TEXT NOT NULL,
    details JSONB,
    resolved BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.provider_health (
    provider TEXT NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ok BOOLEAN NOT NULL,
    latency_ms INT,
    detail TEXT,
    PRIMARY KEY (provider, checked_at)
);
