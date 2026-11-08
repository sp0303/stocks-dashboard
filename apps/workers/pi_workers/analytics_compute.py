"""Client analytics precompute (HLD D1): ledger + market + portfolio.client_daily in,
one JSONB row per client in portfolio.client_analytics out.

Runs inside portfolio-worker right after a client's portfolio recompute, so the
daily series it reads is the one just written (R5: one engine, one series). All
math is pi_core's (``pi_core.analytics.client_report``); this module only does I/O.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping
from datetime import date, timedelta
from typing import Any
from uuid import UUID

import asyncpg
from pi_core.analytics.client_report import (
    BenchmarkInput,
    DailyRow,
    ReportInputs,
    build_client_report,
    closed_round_trips,
)
from pi_core.analytics.exposure import SecurityClass

from pi_workers.portfolio_compute import (
    actions_from_rows,
    build_price_lookup,
    engine_calendar,
    trades_from_rows,
)

logger = logging.getLogger("pi_workers.analytics")

ANALYTICS_VERSION = "a1"
# Display order for the benchmark picker; any other active benchmark follows.
BENCHMARK_ORDER = ("^NSEI", "NIFTYMIDCAP150.NS", "^CNX100", "NIFTYSMLCAP250.NS")

_TRADES_SQL = """
    SELECT trade_id, trade_date, symbol, exchange, trade_type, quantity, price,
           charges, segment, extra, source, note
    FROM ledger.trades
    WHERE client_id = $1 AND deleted_at IS NULL
    ORDER BY trade_date, trade_id
"""
_PRICES_SQL = """
    SELECT s.symbol, s.exchange, e.price_date, e.close::float8 AS close
    FROM market.eod_prices e JOIN market.securities s USING (security_id)
    WHERE s.symbol = ANY($1::text[]) AND e.price_date >= $2::date - 30
"""
_DAILY_SQL = """
    SELECT as_of, market_value::float8 AS market_value, net_invested::float8 AS net_invested,
           nav, day_return, coalesce(unpriced_cost, 0)::float8 AS unpriced_cost
    FROM portfolio.client_daily
    WHERE client_id = $1 AND as_of >= $2
    ORDER BY as_of
"""
_BENCH_VALUES_SQL = """
    SELECT benchmark_id, value_date, value::float8 AS value
    FROM market.benchmark_values
    WHERE benchmark_id = ANY($1::smallint[]) AND value_date >= $2 AND value_date <= $3
"""
_UPSERT_SQL = """
    INSERT INTO portfolio.client_analytics (client_id, as_of, payload, engine_version, computed_at)
    VALUES ($1, $2, $3::jsonb, $4, now())
    ON CONFLICT (client_id) DO UPDATE
    SET as_of = EXCLUDED.as_of, payload = EXCLUDED.payload,
        engine_version = EXCLUDED.engine_version, computed_at = now()
"""


def notes_by_trade(trade_rows: Iterable[Mapping[str, Any]], journal: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """research.trade_notes wins over ledger.trades.note; system 'derived:' notes are skipped."""
    out = {
        str(r["trade_id"]): r["note"]
        for r in trade_rows
        if r.get("note") and not str(r["note"]).startswith("derived:")
    }
    out.update({str(r["trade_id"]): r["note"] for r in journal if r.get("note")})
    return out


def manual_rows(trade_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Opening / adjustment trades entered by hand (source = 'manual')."""
    return [
        {
            "trade_id": int(r["trade_id"]),
            "trade_date": r["trade_date"].isoformat(),
            "symbol": r["symbol"],
            "exchange": r["exchange"],
            "side": str(r["trade_type"]).upper(),
            "quantity": float(r["quantity"]),
            "price": float(r["price"]),
            "note": r.get("note"),
        }
        for r in trade_rows
        if r.get("source") == "manual"
    ]


def order_benchmarks(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    rank = {c: i for i, c in enumerate(BENCHMARK_ORDER)}
    return sorted(rows, key=lambda r: (rank.get(r["code"], len(rank)), r["code"]))


async def _benchmarks(conn: asyncpg.Connection, first: date, today: date) -> list[BenchmarkInput]:
    meta = order_benchmarks(
        await conn.fetch(
            "SELECT benchmark_id, code, label, is_tri FROM market.benchmarks WHERE is_active"
        )
    )
    if not meta:
        return []
    values = await conn.fetch(_BENCH_VALUES_SQL, [m["benchmark_id"] for m in meta], first, today)
    levels: dict[int, dict[date, float]] = {}
    for v in values:
        levels.setdefault(v["benchmark_id"], {})[v["value_date"]] = float(v["value"])
    return [
        BenchmarkInput(m["code"], m["label"], bool(m["is_tri"]), levels.get(m["benchmark_id"], {}))
        for m in meta
    ]


async def _reference(conn: asyncpg.Connection, client_id: UUID, symbols: list[str], first: date):
    ca = await conn.fetch(
        "SELECT symbol, type, ex_date, qty_multiplier FROM ledger.corporate_actions "
        "WHERE symbol = ANY($1::text[]) AND ex_date >= $2 ORDER BY ex_date",
        symbols,
        first,
    )
    px = await conn.fetch(_PRICES_SQL, symbols, first)
    sec = await conn.fetch(
        "SELECT symbol, exchange, sector, cap, asset_class FROM market.securities "
        "WHERE symbol = ANY($1::text[])",
        symbols,
    )
    journal = await conn.fetch(
        "SELECT trade_id, note FROM research.trade_notes WHERE client_id = $1", client_id
    )
    classes = {
        (r["symbol"], r["exchange"]): SecurityClass(r["sector"], r["cap"], r["asset_class"])
        for r in sec
    }
    prices = [(r["symbol"], r["exchange"], r["price_date"], r["close"]) for r in px]
    return ca, prices, classes, journal


async def load_report_inputs(
    conn: asyncpg.Connection, client_id: UUID, today: date, closed_days: set[date]
) -> ReportInputs | None:
    rows = await conn.fetch(_TRADES_SQL, client_id)
    if not rows:
        return None
    first = min(r["trade_date"] for r in rows)
    symbols = sorted({r["symbol"] for r in rows})
    ca, prices, classes, journal = await _reference(conn, client_id, symbols, first)
    daily = await conn.fetch(_DAILY_SQL, client_id, first - timedelta(days=1))
    return ReportInputs(
        trades=trades_from_rows(rows),
        actions=actions_from_rows(ca),
        calendar=engine_calendar(first, today, closed_days),
        price_lookup=build_price_lookup(prices),
        today=today,
        classes=classes,
        notes=notes_by_trade(rows, journal),
        manual_trades=manual_rows(rows),
        daily=[
            DailyRow(r["as_of"], float(r["market_value"]), float(r["net_invested"]), float(r["nav"]), r["day_return"], float(r["unpriced_cost"]))
            for r in daily
        ],
        benchmarks=await _benchmarks(conn, first - timedelta(days=10), today),
    )


_ROUND_TRIPS_SQL = """
    INSERT INTO portfolio.round_trips (client_id, symbol, buy_date, sell_date, quantity, buy_price, sell_price, pnl, days)
    SELECT $1, t.symbol, t.buy_date, t.sell_date, t.quantity, t.buy_price, t.sell_price, t.pnl, t.days
    FROM unnest($2::text[], $3::date[], $4::date[], $5::numeric[], $6::numeric[], $7::numeric[], $8::numeric[], $9::int[])
         AS t(symbol, buy_date, sell_date, quantity, buy_price, sell_price, pnl, days)
"""


async def _replace_round_trips(conn: asyncpg.Connection, client_id: UUID, rows: list[dict[str, Any]]) -> None:
    """Replace this client's closed round trips (derived data, rebuilt on every recompute)."""
    await conn.execute("DELETE FROM portfolio.round_trips WHERE client_id = $1", client_id)
    if rows:
        cols = [[r[k] for r in rows] for k in ("symbol", "buy_date", "sell_date", "quantity", "buy_price", "sell_price", "pnl", "days")]
        await conn.execute(_ROUND_TRIPS_SQL, client_id, *cols)


async def recompute_client_analytics(
    conn: asyncpg.Connection, client_id: UUID, today: date, closed_days: set[date]
) -> bool:
    """Rebuilds (or clears) one client's analytics row. Idempotent: an upsert on client_id."""
    inputs = await load_report_inputs(conn, client_id, today, closed_days)
    if inputs is None:
        await conn.execute("DELETE FROM portfolio.client_analytics WHERE client_id = $1", client_id)
        await _replace_round_trips(conn, client_id, [])
        return True
    payload = build_client_report(inputs)
    await conn.execute(_UPSERT_SQL, client_id, today, json.dumps(payload, default=str), ANALYTICS_VERSION)
    await _replace_round_trips(conn, client_id, closed_round_trips(inputs))
    return True


async def recompute_client_analytics_safe(
    conn: asyncpg.Connection, client_id: UUID, today: date, closed_days: set[date]
) -> bool:
    """Analytics must never fail the portfolio recompute that precedes it."""
    try:
        return await recompute_client_analytics(conn, client_id, today, closed_days)
    except Exception:
        logger.exception("client analytics recompute failed")
        return False
