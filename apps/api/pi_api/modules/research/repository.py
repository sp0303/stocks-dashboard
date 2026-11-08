"""Research repository: SQL queries on watchlists, board items, theses, and screener."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List, Optional
from uuid import UUID
import asyncpg


class ResearchRepository:

    @staticmethod
    async def get_watchlist_owner(conn: asyncpg.Connection, watchlist_id: UUID) -> Optional[UUID]:
        return await conn.fetchval(
            "SELECT owner_id FROM research.watchlists WHERE watchlist_id = $1;", watchlist_id
        )

    @staticmethod
    async def get_board_item_owner(conn: asyncpg.Connection, item_id: UUID) -> Optional[UUID]:
        return await conn.fetchval(
            "SELECT owner_id FROM research.board_items WHERE item_id = $1;", item_id
        )

    @staticmethod
    async def list_watchlists(conn: asyncpg.Connection, owner_id: UUID) -> List[Dict[str, Any]]:
        # Sector: the entry's own, else the security master, else the latest screener
        # snapshot's NSE industry (v1's sector map rides in that payload).
        query = """
            WITH snap AS (
                SELECT payload FROM research.screener_snapshots
                WHERE as_of >= CURRENT_DATE - INTERVAL '3650 days'
                ORDER BY as_of DESC, (model = 'v1_daily') DESC, model
                LIMIT 1
            ), snap_sector AS (
                SELECT DISTINCT ON (sym) sym, sector FROM (
                    SELECT upper(COALESCE(x->>'ticker', x->>'symbol')) AS sym,
                           NULLIF(x->>'sector', '') AS sector
                    FROM snap,
                         jsonb_array_elements(CASE jsonb_typeof(snap.payload)
                             WHEN 'array' THEN snap.payload
                             ELSE COALESCE(snap.payload->'stocks', '[]'::jsonb) END) x
                ) t WHERE sym IS NOT NULL AND sector IS NOT NULL
                ORDER BY sym
            )
            SELECT
                w.watchlist_id, w.owner_type, w.owner_id, w.name, w.is_default,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'symbol', e.symbol,
                            'added_date', e.added_date,
                            'added_price', e.added_price::FLOAT,
                            'why', e.why,
                            'remarks', e.remarks,
                            'risks', e.risks,
                            'sector', COALESCE(NULLIF(e.sector, ''), sec.sector, ss.sector),
                            'alert_price', e.alert_price::FLOAT,
                            'alert_date', e.alert_date
                        ) ORDER BY e.added_date, e.symbol
                    ) FILTER (WHERE e.symbol IS NOT NULL), '[]'
                ) AS entries
            FROM research.watchlists w
            LEFT JOIN research.watchlist_entries e ON w.watchlist_id = e.watchlist_id
            LEFT JOIN LATERAL (
                SELECT NULLIF(s.sector, '') AS sector FROM market.securities s
                WHERE s.symbol = upper(e.symbol) AND NULLIF(s.sector, '') IS NOT NULL
                ORDER BY (s.exchange = 'NSE') DESC LIMIT 1
            ) sec ON true
            LEFT JOIN snap_sector ss ON ss.sym = upper(e.symbol)
            WHERE w.owner_id = $1
            GROUP BY w.watchlist_id, w.owner_type, w.owner_id, w.name, w.is_default
            ORDER BY w.is_default DESC, w.name ASC;
        """
        rows = await conn.fetch(query, owner_id)
        results = []
        for r in rows:
            entries = json.loads(r["entries"]) if isinstance(r["entries"], str) else r["entries"]
            results.append({
                "watchlist_id": r["watchlist_id"],
                "owner_type": r["owner_type"],
                "owner_id": r["owner_id"],
                "name": r["name"],
                "is_default": r["is_default"],
                "entries": entries,
            })
        return results

    @staticmethod
    async def create_watchlist(
        conn: asyncpg.Connection,
        owner_type: str,
        owner_id: UUID,
        name: str,
        is_default: bool = False,
    ) -> Dict[str, Any]:
        query = """
            INSERT INTO research.watchlists (owner_type, owner_id, name, is_default)
            VALUES ($1, $2, $3, $4)
            RETURNING watchlist_id, owner_type, owner_id, name, is_default;
        """
        row = await conn.fetchrow(query, owner_type, owner_id, name, is_default)
        return {**dict(row), "entries": []}

    @staticmethod
    async def add_watchlist_entry(
        conn: asyncpg.Connection,
        watchlist_id: UUID,
        symbol: str,
        added_price: Optional[float] = None,
        why: Optional[str] = None,
        remarks: Optional[str] = None,
        risks: Optional[str] = None,
        sector: Optional[str] = None,
        alert_price: Optional[float] = None,
    ) -> None:
        query = """
            INSERT INTO research.watchlist_entries (
                watchlist_id, symbol, added_date, added_price, why, remarks, risks, sector, alert_price
            )
            VALUES ($1, $2, CURRENT_DATE, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (watchlist_id, symbol) DO UPDATE SET
                added_price = EXCLUDED.added_price,
                why = EXCLUDED.why,
                remarks = EXCLUDED.remarks,
                risks = EXCLUDED.risks,
                sector = EXCLUDED.sector,
                alert_price = EXCLUDED.alert_price;
        """
        await conn.execute(query, watchlist_id, symbol.upper(), added_price, why, remarks, risks, sector, alert_price)

    @staticmethod
    async def delete_watchlist_entry(conn: asyncpg.Connection, watchlist_id: UUID, symbol: str) -> None:
        query = "DELETE FROM research.watchlist_entries WHERE watchlist_id = $1 AND symbol = $2;"
        await conn.execute(query, watchlist_id, symbol.upper())

    @staticmethod
    async def list_board_items(conn: asyncpg.Connection, owner_id: UUID) -> List[Dict[str, Any]]:
        query = """
            SELECT item_id, owner_type, owner_id, symbol, lane,
                   entry_price::FLOAT, exit_price::FLOAT, why, colour, sort_order
            FROM research.board_items
            WHERE owner_id = $1
            ORDER BY sort_order ASC, symbol ASC;
        """
        rows = await conn.fetch(query, owner_id)
        return [dict(r) for r in rows]

    @staticmethod
    async def create_board_item(
        conn: asyncpg.Connection,
        owner_type: str,
        owner_id: UUID,
        symbol: str,
        lane: str,
        entry_price: Optional[float] = None,
        exit_price: Optional[float] = None,
        why: Optional[str] = None,
        colour: Optional[str] = None,
        sort_order: int = 0,
    ) -> Dict[str, Any]:
        query = """
            INSERT INTO research.board_items (
                owner_type, owner_id, symbol, lane, entry_price, exit_price, why, colour, sort_order
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING item_id, owner_type, owner_id, symbol, lane, entry_price::FLOAT, exit_price::FLOAT, why, colour, sort_order;
        """
        row = await conn.fetchrow(query, owner_type, owner_id, symbol.upper(), lane, entry_price, exit_price, why, colour, sort_order)
        return dict(row)

    @staticmethod
    async def update_board_item(
        conn: asyncpg.Connection,
        item_id: UUID,
        lane: Optional[str] = None,
        entry_price: Optional[float] = None,
        exit_price: Optional[float] = None,
        why: Optional[str] = None,
        colour: Optional[str] = None,
        sort_order: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        query = """
            UPDATE research.board_items
            SET 
                lane = COALESCE($2, lane),
                entry_price = COALESCE($3, entry_price),
                exit_price = COALESCE($4, exit_price),
                why = COALESCE($5, why),
                colour = COALESCE($6, colour),
                sort_order = COALESCE($7, sort_order)
            WHERE item_id = $1
            RETURNING item_id, owner_type, owner_id, symbol, lane, entry_price::FLOAT, exit_price::FLOAT, why, colour, sort_order;
        """
        row = await conn.fetchrow(query, item_id, lane, entry_price, exit_price, why, colour, sort_order)
        return dict(row) if row else None

    @staticmethod
    async def delete_board_item(conn: asyncpg.Connection, item_id: UUID) -> None:
        query = "DELETE FROM research.board_items WHERE item_id = $1;"
        await conn.execute(query, item_id)

    @staticmethod
    async def get_stock_thesis(conn: asyncpg.Connection, client_id: UUID, symbol: str) -> Optional[Dict[str, Any]]:
        query = """
            SELECT client_id, symbol, thesis, updated_at
            FROM research.stock_theses
            WHERE client_id = $1 AND symbol = $2;
        """
        row = await conn.fetchrow(query, client_id, symbol.upper())
        if not row:
            return None
        thesis = json.loads(row["thesis"]) if isinstance(row["thesis"], str) else row["thesis"]
        return {
            "client_id": row["client_id"],
            "symbol": row["symbol"],
            "thesis": thesis,
            "updated_at": row["updated_at"],
        }

    @staticmethod
    async def upsert_stock_thesis(conn: asyncpg.Connection, client_id: UUID, symbol: str, thesis: Dict[str, Any]) -> Dict[str, Any]:
        query = """
            INSERT INTO research.stock_theses (client_id, symbol, thesis, updated_at)
            VALUES ($1, $2, $3, now())
            ON CONFLICT (client_id, symbol) DO UPDATE SET
                thesis = EXCLUDED.thesis,
                updated_at = now()
            RETURNING client_id, symbol, thesis, updated_at;
        """
        row = await conn.fetchrow(query, client_id, symbol.upper(), json.dumps(thesis))
        res_thesis = json.loads(row["thesis"]) if isinstance(row["thesis"], str) else row["thesis"]
        return {
            "client_id": row["client_id"],
            "symbol": row["symbol"],
            "thesis": res_thesis,
            "updated_at": row["updated_at"],
        }

    @staticmethod
    async def get_latest_screener_snapshot(conn: asyncpg.Connection, model: Optional[str]) -> Optional[Dict[str, Any]]:
        query = """
            SELECT as_of, model, payload
            FROM research.screener_snapshots
            WHERE ($1::TEXT IS NULL OR model = $1)
              AND as_of >= CURRENT_DATE - INTERVAL '3650 days'
            ORDER BY as_of DESC, (model = 'v1_daily') DESC, model
            LIMIT 1;
        """
        row = await conn.fetchrow(query, model)
        if not row:
            return None
        payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
        return {"as_of": row["as_of"], "model": row["model"], "payload": payload}

    @staticmethod
    async def list_screener_snapshots(conn: asyncpg.Connection) -> List[Dict[str, Any]]:
        query = """
            SELECT as_of, model FROM research.screener_snapshots
            WHERE as_of >= CURRENT_DATE - INTERVAL '3650 days'
            ORDER BY as_of DESC, model LIMIT 100;
        """
        rows = await conn.fetch(query)
        return [dict(r) for r in rows]

    @staticmethod
    async def get_security_sectors(conn: asyncpg.Connection, symbols: List[str]) -> Dict[str, str]:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (symbol) symbol, sector FROM market.securities
            WHERE symbol = ANY($1::text[]) AND NULLIF(sector, '') IS NOT NULL
            ORDER BY symbol, (exchange = 'NSE') DESC;
            """,
            symbols,
        )
        return {r["symbol"]: r["sector"] for r in rows}
