"""Ledger service layer: Trade queries, upload reject reporting, and CSV export (Rule R14)."""

from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from datetime import date
from typing import Any, Awaitable, Callable, Dict, List, Optional
from uuid import UUID
import asyncpg

from pi_api.modules.ledger import dividend_suggestions
from pi_api.modules.ledger.repository import LedgerRepository


logger = logging.getLogger("pi_api.ledger")

Recompute = Callable[[asyncpg.Connection, UUID], Awaitable[Any]]


def _norm_side(side: Optional[str]) -> Optional[str]:
    return side.strip().lower() if side and side.strip() else None


class LedgerService:

    def __init__(self, repo: LedgerRepository = LedgerRepository()) -> None:
        self.repo = repo

    async def list_trades(
        self,
        conn: asyncpg.Connection,
        client_id: UUID,
        symbol: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        return await self.repo.list_trades(conn, client_id, symbol, start_date, end_date, limit, offset)

    async def list_trades_by_side(
        self, conn: asyncpg.Connection, client_id: UUID, symbol: Optional[str], side: Optional[str],
        start_date: Optional[date], end_date: Optional[date], limit: int, offset: int,
    ) -> List[Dict[str, Any]]:
        return await self.repo.list_trades(
            conn, client_id, symbol, start_date, end_date, limit, offset, _norm_side(side)
        )

    async def list_manager_trades(
        self,
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
        return await self.repo.list_manager_trades(
            conn, manager_id, client_id, symbol, _norm_side(side), start_date, end_date, limit, offset
        )

    async def list_corporate_actions(
        self,
        conn: asyncpg.Connection,
        symbol: Optional[str] = None,
        action_type: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        return await self.repo.list_corporate_actions(
            conn, symbol, action_type, start_date, end_date, limit, offset
        )


    # --- Dividends ---
    async def list_dividends(self, conn: asyncpg.Connection, client_id: UUID) -> List[Dict[str, Any]]:
        return await self.repo.list_dividends(conn, client_id)

    async def add_dividend(self, conn: asyncpg.Connection, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self.repo.insert_dividend(
            conn, data["client_id"], data["symbol"].strip().upper(), data["ex_date"],
            data["amount_per_share"], data["quantity"],
        )

    async def suggest_dividends(self, conn: asyncpg.Connection, client_id: UUID) -> List[Dict[str, Any]]:
        """Proposals only; nothing is written until the user accepts a row (POST /dividends)."""
        inp = await self.repo.dividend_suggestion_inputs(conn, client_id)
        return dividend_suggestions.suggest(inp["trades"], inp["actions"], inp["existing"])

    async def get_dividend_owner(self, conn: asyncpg.Connection, dividend_id: int) -> Optional[Dict[str, Any]]:
        return await self.repo.get_dividend_owner(conn, dividend_id)

    async def delete_dividend(self, conn: asyncpg.Connection, dividend_id: int) -> bool:
        return await self.repo.delete_manual_dividend(conn, dividend_id)

    # --- Manual trades ---
    @staticmethod
    async def _safe_recompute(conn: asyncpg.Connection, client_id: UUID, recompute: Optional[Recompute]) -> bool:
        if recompute is None:
            return False
        try:
            await recompute(conn, client_id)
            return True
        except Exception:  # recompute failure must not lose the ledger write
            logger.exception("Portfolio recompute failed for client %s", client_id)
            return False

    async def add_manual_trade(
        self, conn: asyncpg.Connection, data: Dict[str, Any], recompute: Optional[Recompute] = None
    ) -> Dict[str, Any]:
        t = {**data, "symbol": data["symbol"].strip().upper()}
        key = data.get("idempotency_key") or uuid.uuid4().hex
        trade_id = await self.repo.insert_manual_trade(conn, f"manual_{key}", t)
        created = trade_id is not None
        recomputed = await self._safe_recompute(conn, t["client_id"], recompute) if created else False
        return {"trade_id": trade_id, "created": created, "recomputed": recomputed}

    async def get_trade_owner(self, conn: asyncpg.Connection, trade_id: int) -> Optional[Dict[str, Any]]:
        return await self.repo.get_trade_owner(conn, trade_id)

    async def void_manual_trade(
        self, conn: asyncpg.Connection, trade_id: int, client_id: UUID, recompute: Optional[Recompute] = None
    ) -> Dict[str, Any]:
        voided = await self.repo.void_manual_trade(conn, trade_id)
        recomputed = await self._safe_recompute(conn, client_id, recompute) if voided else False
        return {"trade_id": trade_id, "voided": voided, "recomputed": recomputed}

    async def list_uploads(self, conn: asyncpg.Connection, client_id: UUID) -> List[Dict[str, Any]]:
        return await self.repo.list_uploads(conn, client_id)

    async def get_rejects(self, conn: asyncpg.Connection, upload_id: UUID) -> List[Dict[str, Any]]:
        return await self.repo.get_upload_rejects(conn, upload_id)

    async def generate_export_csv(self, conn: asyncpg.Connection, client_id: UUID) -> str:
        """Generates lossless broker-compatible tradebook CSV adhering to Rule R14.

        Ids written as text, auction as lowercase boolean, exact precision preserved.
        """
        trades = await self.repo.get_trades_for_export(conn, client_id)
        output = io.StringIO()
        writer = csv.writer(output)

        headers = [
            "symbol", "isin", "trade_date", "exchange", "segment", "series",
            "trade_type", "auction", "quantity", "price", "trade_value",
            "order_id", "trade_id"
        ]
        writer.writerow(headers)

        for t in trades:
            writer.writerow([
                t["symbol"],
                t["isin"] or "",
                str(t["trade_date"]),
                t["exchange"],
                t["segment"],
                t["series"] or "",
                t["trade_type"],
                "true" if t["auction"] else "false",  # lowercase boolean (Rule R14)
                f"{t['quantity']:.6f}".rstrip("0").rstrip("."),
                f"{t['price']:.4f}",
                f"{t['trade_value']:.4f}",
                f"'{t['broker_order_id']}" if t["broker_order_id"] else "",  # quote text ID (Rule R14)
                f"'{t['broker_trade_id']}" if t["broker_trade_id"] else "",
            ])

        return output.getvalue()
