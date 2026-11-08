"""Manager-book service: roster CRUD rules and read-model assembly."""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from uuid import UUID

import asyncpg

from pi_api.modules.admin import book_math
from pi_api.modules.admin.book_repository import BookRepository
from pi_api.modules.admin.clients_repository import ClientsRepository

EPOCH = date(1990, 1, 1)
_OVERVIEW_KEYS = (
    "market_value",
    "capital_deployed",
    "current_invested",
    "realized_pnl",
    "unrealized_pnl",
    "total_pnl",
    "return_on_capital",
)


class BookError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _payload(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    return json.loads(raw) if isinstance(raw, (str, bytes)) else dict(raw)


def _roster_item(r: dict[str, Any]) -> dict[str, Any]:
    p = _payload(r.get("payload"))
    item = {
        k: r.get(k)
        for k in ("client_id", "name", "client_code", "broker", "status", "as_of")
    }
    item["trade_count"] = int(r.get("trade_count") or 0)
    item["computed"] = bool(p)
    for k in _OVERVIEW_KEYS:
        item[k] = p.get(k)  # None when the worker has not computed this client yet
    return item


class BookService:
    def __init__(
        self,
        repo: BookRepository | None = None,
        clients: ClientsRepository | None = None,
    ) -> None:
        self.repo = repo or BookRepository()
        self.clients = clients or ClientsRepository()

    # ---------------------------------------------------------------- read models
    async def summary(
        self, conn: asyncpg.Connection, manager_id: UUID
    ) -> dict[str, Any]:
        roster = [_roster_item(r) for r in await self.repo.roster(conn, manager_id)]
        positions = await self.repo.positions(conn, manager_id)
        counts = await self.repo.trade_counts(conn, manager_id, EPOCH)
        as_of = max((c["as_of"] for c in roster if c["as_of"]), default=None)
        return {
            "manager_id": manager_id,
            "as_of": as_of,
            "totals": book_math.book_totals(roster),
            "insights": book_math.book_insights(positions, counts),
            "clients": roster,
        }

    async def performance(
        self, conn: asyncpg.Connection, manager_id: UUID, codes: list[str], since: date
    ) -> dict[str, Any]:
        book = await self.repo.book_series(conn, manager_id, since)
        codes = codes or await self.repo.active_benchmark_codes(conn)
        values = await self.repo.benchmark_values(conn, codes, since) if book else []
        by_code: dict[str, dict[str, Any]] = {}
        for v in values:
            b = by_code.setdefault(v["code"], {"label": v["label"], "values": {}})
            b["values"][v["value_date"]] = v["value"]
        benchmarks = []
        for code in codes:
            entry = by_code.get(code, {"label": code, "values": {}})
            res = book_math.index_units(book, entry["values"])
            benchmarks.append({"code": code, "label": entry["label"], **res})
        return {
            "dates": [r["as_of"] for r in book],
            "book_pnl": [
                float(r["market_value"]) - float(r["net_invested"]) for r in book
            ],
            "net_invested": [float(r["net_invested"]) for r in book],
            "benchmarks": benchmarks,
        }

    async def client_returns(
        self, conn: asyncpg.Connection, manager_id: UUID, since: date
    ) -> list[dict[str, Any]]:
        return book_math.client_returns(
            await self.repo.client_navs(conn, manager_id, since)
        )

    async def closed_trades(
        self, conn: asyncpg.Connection, manager_id: UUID, since: date, limit: int
    ) -> list[dict[str, Any]]:
        rows = await self.repo.closed_trades(conn, manager_id, since, limit)
        for r in rows:
            cost = r["buy_price"] * r["quantity"]
            r["pnl_pct"] = r["pnl"] / cost if cost > 0 else None
        return rows

    # ---------------------------------------------------------------- roster CRUD
    async def create_client(
        self,
        conn: asyncpg.Connection,
        manager_id: UUID,
        name: str,
        code: str | None,
        broker: str | None,
    ) -> dict[str, Any]:
        if not await self.clients.manager_exists(conn, manager_id):
            raise BookError(404, "Manager not found.")
        if code and await self.clients.code_taken(conn, manager_id, code):
            raise BookError(
                409,
                "That broker code is already used by another client of this manager.",
            )
        return await self.clients.create_client(conn, manager_id, name, code, broker)

    async def get_client(
        self, conn: asyncpg.Connection, client_id: UUID
    ) -> dict[str, Any]:
        row = await self.clients.get_client(conn, client_id)
        if not row:
            raise BookError(404, "Client not found.")
        return row

    async def update_client(
        self, conn: asyncpg.Connection, current: dict[str, Any], changes: dict[str, Any]
    ) -> dict[str, Any]:
        target_mgr = changes.get("manager_id", current["manager_id"])
        if "manager_id" in changes and not await self.clients.manager_exists(
            conn, target_mgr
        ):
            raise BookError(404, "Target manager not found.")
        code = changes.get("client_code", current["client_code"])
        if code and await self.clients.code_taken(
            conn, target_mgr, code, current["client_id"]
        ):
            raise BookError(
                409,
                "That broker code is already used by another client of this manager.",
            )
        row = await self.clients.update_client(conn, current["client_id"], changes)
        if not row:
            raise BookError(404, "Client not found.")
        return row

    async def delete_client(self, conn: asyncpg.Connection, client_id: UUID) -> None:
        if not await self.clients.soft_delete_client(conn, client_id):
            raise BookError(404, "Client not found.")
