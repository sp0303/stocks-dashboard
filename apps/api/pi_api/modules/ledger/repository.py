"""Ledger repository: SQL queries on ledger.trades, uploads, and rejects."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List, Optional
from uuid import UUID
import asyncpg


class LedgerRepository:

    @staticmethod
    async def list_trades(
        conn: asyncpg.Connection,
        client_id: UUID,
        symbol: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100,
        offset: int = 0,
        side: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT 
                trade_id, client_id, symbol, exchange, trade_date, trade_type,
                quantity::FLOAT, price::FLOAT, trade_value::FLOAT,
                charges::FLOAT, charges_known, segment, broker_trade_id,
                broker_order_id, source, created_at
            FROM ledger.trades
            WHERE client_id = $1
              AND deleted_at IS NULL
              AND ($2::TEXT IS NULL OR symbol = $2)
              AND ($3::DATE IS NULL OR trade_date >= $3)
              AND ($4::DATE IS NULL OR trade_date <= $4)
              AND ($7::TEXT IS NULL OR trade_type = $7)
            ORDER BY trade_date DESC, trade_id DESC
            LIMIT $5 OFFSET $6;
        """
        rows = await conn.fetch(query, client_id, symbol, start_date, end_date, limit, offset, side)
        return [dict(r) for r in rows]

    @staticmethod
    async def list_uploads(conn: asyncpg.Connection, client_id: UUID) -> List[Dict[str, Any]]:
        query = """
            SELECT upload_id, client_id, file_name, broker_format,
                   rows_total, rows_imported, rows_duplicate, rows_rejected,
                   status, uploaded_at
            FROM ledger.uploads
            WHERE client_id = $1
            ORDER BY uploaded_at DESC;
        """
        rows = await conn.fetch(query, client_id)
        return [dict(r) for r in rows]

    @staticmethod
    async def get_upload_rejects(conn: asyncpg.Connection, upload_id: UUID) -> List[Dict[str, Any]]:
        query = """
            SELECT upload_id, row_no, reason, raw
            FROM ledger.upload_rejects
            WHERE upload_id = $1
            ORDER BY row_no ASC;
        """
        rows = await conn.fetch(query, upload_id)
        return [
            {
                "upload_id": r["upload_id"],
                "row_no": r["row_no"],
                "reason": r["reason"],
                "raw": json.loads(r["raw"]) if isinstance(r["raw"], str) else r["raw"],
            }
            for r in rows
        ]

    @staticmethod
    async def get_trades_for_export(conn: asyncpg.Connection, client_id: UUID) -> List[Dict[str, Any]]:
        """Extracts complete trades for lossless CSV export (Rule R14)."""
        query = """
            SELECT 
                symbol, isin, trade_date, exchange, segment, series,
                trade_type, auction, quantity::FLOAT, price::FLOAT,
                trade_value::FLOAT, broker_order_id, broker_trade_id,
                charges::FLOAT, extra
            FROM ledger.trades
            WHERE client_id = $1 AND deleted_at IS NULL
            ORDER BY trade_date ASC, trade_id ASC;
        """
        rows = await conn.fetch(query, client_id)
        return [dict(r) for r in rows]

    @staticmethod
    async def list_manager_trades(
        conn: asyncpg.Connection,
        manager_id: UUID,
        client_id: Optional[UUID] = None,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT 
                t.trade_id, t.client_id, c.name AS client_name, c.client_code,
                t.symbol, t.exchange, t.trade_date, t.trade_type,
                t.quantity::FLOAT, t.price::FLOAT, t.trade_value::FLOAT,
                t.charges::FLOAT, t.charges_known, t.segment, t.broker_trade_id,
                t.broker_order_id, t.source, t.created_at
            FROM ledger.trades t
            JOIN core.clients c ON t.client_id = c.client_id
            WHERE c.manager_id = $1
              AND t.deleted_at IS NULL
              AND ($2::UUID IS NULL OR t.client_id = $2)
              AND ($3::TEXT IS NULL OR t.symbol = $3)
              AND ($4::TEXT IS NULL OR t.trade_type = $4)
              AND ($5::DATE IS NULL OR t.trade_date >= $5)
              AND ($6::DATE IS NULL OR t.trade_date <= $6)
            ORDER BY t.trade_date DESC, t.trade_id DESC
            LIMIT $7 OFFSET $8;
        """
        rows = await conn.fetch(query, manager_id, client_id, symbol, side, start_date, end_date, limit, offset)
        return [dict(r) for r in rows]

    @staticmethod
    async def list_corporate_actions(
        conn: asyncpg.Connection,
        symbol: Optional[str] = None,
        action_type: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT 
                action_id, key, isin, symbol, ex_date, type,
                qty_multiplier::FLOAT, amount_per_share::FLOAT, subject, source, fetched_at
            FROM ledger.corporate_actions
            WHERE ($1::TEXT IS NULL OR symbol = $1)
              AND ($2::TEXT IS NULL OR type = $2)
              AND ($3::DATE IS NULL OR ex_date >= $3)
              AND ($4::DATE IS NULL OR ex_date <= $4)
            ORDER BY ex_date DESC, action_id DESC
            LIMIT $5 OFFSET $6;
        """
        rows = await conn.fetch(query, symbol, action_type, start_date, end_date, limit, offset)
        return [dict(r) for r in rows]


    # --- Dividends (ledger.dividends) ---
    @staticmethod
    async def list_dividends(conn: asyncpg.Connection, client_id: UUID) -> List[Dict[str, Any]]:
        query = """
            SELECT dividend_id, client_id, symbol, ex_date,
                   amount_per_share::FLOAT, quantity::FLOAT,
                   (amount_per_share * quantity)::FLOAT AS amount, source
            FROM ledger.dividends
            WHERE client_id = $1
            ORDER BY ex_date DESC, dividend_id DESC
            LIMIT 1000;
        """
        rows = await conn.fetch(query, client_id)
        return [dict(r) for r in rows]

    @staticmethod
    async def insert_dividend(
        conn: asyncpg.Connection, client_id: UUID, symbol: str, ex_date: date,
        amount_per_share: float, quantity: float,
    ) -> Dict[str, Any]:
        query = """
            INSERT INTO ledger.dividends (client_id, symbol, ex_date, amount_per_share, quantity, source)
            VALUES ($1, $2, $3, $4, $5, 'manual')
            RETURNING dividend_id, client_id, symbol, ex_date,
                      amount_per_share::FLOAT, quantity::FLOAT,
                      (amount_per_share * quantity)::FLOAT AS amount, source;
        """
        row = await conn.fetchrow(query, client_id, symbol, ex_date, amount_per_share, quantity)
        return dict(row)

    @staticmethod
    async def get_dividend_owner(conn: asyncpg.Connection, dividend_id: int) -> Optional[Dict[str, Any]]:
        row = await conn.fetchrow(
            "SELECT client_id, source FROM ledger.dividends WHERE dividend_id = $1;", dividend_id
        )
        return dict(row) if row else None

    @staticmethod
    async def delete_manual_dividend(conn: asyncpg.Connection, dividend_id: int) -> bool:
        status = await conn.execute(
            "DELETE FROM ledger.dividends WHERE dividend_id = $1 AND source = 'manual';", dividend_id
        )
        return status.endswith(" 1")

    @staticmethod
    async def dividend_suggestion_inputs(conn: asyncpg.Connection, client_id: UUID) -> Dict[str, Any]:
        """Live trades, stored DIVIDEND/SPLIT/BONUS actions for the traded symbols, and the
        (symbol, ex_date) pairs already recorded. Time-bounded to the client's first trade."""
        trades = await conn.fetch(
            """
            SELECT upper(symbol) AS symbol, trade_date, trade_type, quantity::FLOAT AS quantity, segment
            FROM ledger.trades
            WHERE client_id = $1 AND deleted_at IS NULL
              AND trade_date >= DATE '1990-01-01'
            ORDER BY trade_date, trade_id;
            """,
            client_id,
        )
        if not trades:
            return {"trades": [], "actions": [], "existing": []}
        symbols = sorted({r["symbol"] for r in trades})
        first = min(r["trade_date"] for r in trades)
        actions = await conn.fetch(
            """
            SELECT upper(symbol) AS symbol, ex_date, type, qty_multiplier::FLOAT AS qty_multiplier,
                   amount_per_share::FLOAT AS amount_per_share, subject, source
            FROM ledger.corporate_actions
            WHERE upper(symbol) = ANY($1::text[]) AND ex_date > $2 AND ex_date <= CURRENT_DATE
              AND type IN ('DIVIDEND', 'SPLIT', 'BONUS')
            ORDER BY ex_date, action_id;
            """,
            symbols,
            first,
        )
        existing = await conn.fetch(
            "SELECT upper(symbol) AS symbol, ex_date FROM ledger.dividends WHERE client_id = $1;",
            client_id,
        )
        return {
            "trades": [dict(r) for r in trades],
            "actions": [dict(r) for r in actions],
            "existing": [(r["symbol"], r["ex_date"]) for r in existing],
        }

    # --- Manual trades (source='manual', Rule R13 append-only: void via deleted_at) ---
    @staticmethod
    async def insert_manual_trade(conn: asyncpg.Connection, fingerprint: str, t: Dict[str, Any]) -> Optional[int]:
        query = """
            INSERT INTO ledger.trades (
                client_id, fingerprint, symbol, trade_date, exchange, segment,
                trade_type, quantity, price, source, note, extra
            )
            VALUES ($1, $2, $3, $4, $5, 'EQ', $6, $7, $8, 'manual', $9, '{}')
            ON CONFLICT (client_id, fingerprint) DO NOTHING
            RETURNING trade_id;
        """
        return await conn.fetchval(
            query, t["client_id"], fingerprint, t["symbol"], t["trade_date"], t["exchange"],
            t["trade_type"], t["quantity"], t["price"], t.get("note"),
        )

    @staticmethod
    async def get_trade_owner(conn: asyncpg.Connection, trade_id: int) -> Optional[Dict[str, Any]]:
        row = await conn.fetchrow(
            "SELECT client_id, source, deleted_at FROM ledger.trades WHERE trade_id = $1;", trade_id
        )
        return dict(row) if row else None

    @staticmethod
    async def void_manual_trade(conn: asyncpg.Connection, trade_id: int) -> bool:
        status = await conn.execute(
            """
            UPDATE ledger.trades SET deleted_at = now()
            WHERE trade_id = $1 AND source = 'manual' AND deleted_at IS NULL;
            """,
            trade_id,
        )
        return status.endswith(" 1")
