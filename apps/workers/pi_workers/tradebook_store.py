"""Set-based tradebook insert + v1-compatible fingerprints (R13, AGENTS §3.8: no per-row loops)."""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from uuid import UUID

import asyncpg

CHUNK = 5000

_INSERT = """
INSERT INTO ledger.trades (
    client_id, fingerprint, symbol, isin, trade_date, exchange, segment, series, trade_type,
    auction, quantity, price, broker_trade_id, broker_order_id, executed_at,
    source, upload_id, extra)
SELECT $1, t.fp, t.symbol, t.isin, t.trade_date, t.exchange, t.segment, t.series, t.trade_type,
       t.auction, t.quantity, t.price, t.btid, t.boid, t.executed_at,
       'upload', $2, t.extra::jsonb
FROM unnest($3::text[], $4::text[], $5::text[], $6::date[], $7::text[], $8::text[], $9::text[],
            $10::text[], $11::bool[], $12::numeric[], $13::numeric[],
            $14::text[], $15::text[], $16::timestamptz[], $17::text[])
     AS t(fp, symbol, isin, trade_date, exchange, segment, series, trade_type, auction,
          quantity, price, btid, boid, executed_at, extra)
ON CONFLICT (client_id, fingerprint) DO NOTHING
RETURNING 1
"""


def fingerprint(client_key: str, r: dict) -> str:
    """Same recipe as v1 ``ingestion._fingerprint`` so re-uploading a file the v1 sync already
    copied dedupes instead of doubling the ledger. ``client_key`` is the account code printed in
    the file, else the client's code, else its id."""
    key = "|".join(
        str(x)
        for x in (client_key, r["trade_date"], r["symbol"], r["trade_type"],
                  r["quantity"], r["price"], r["broker_trade_id"])
    )
    return hashlib.sha1(key.encode()).hexdigest()


def _dec(x: float) -> Decimal:
    return Decimal(str(x))


async def insert_trades(
    conn: asyncpg.Connection, client_id: UUID, upload_id: UUID, rows: list[dict], client_key: str
) -> int:
    """Insert parsed rows idempotently; returns how many were new (the rest were duplicates)."""
    inserted = 0
    for i in range(0, len(rows), CHUNK):
        part = rows[i:i + CHUNK]
        cols: list[list] = [[] for _ in range(15)]
        for r in part:
            vals = (
                fingerprint(client_key, r), r["symbol"], r.get("isin"), r["trade_date"], r["exchange"],
                r["segment"], r.get("series"), r["trade_type"], bool(r.get("auction")),
                _dec(r["quantity"]), _dec(r["price"]),
                r["broker_trade_id"] or None, r.get("broker_order_id") or None,
                r.get("executed_at"), json.dumps(r.get("extra") or {}, default=str),
            )
            for col, v in zip(cols, vals):
                col.append(v)
        got = await conn.fetch(_INSERT, client_id, upload_id, *cols)
        inserted += len(got)
    return inserted
