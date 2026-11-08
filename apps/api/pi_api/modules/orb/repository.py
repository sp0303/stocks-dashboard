"""ORB repository: read-only SQL over orb.* (filled by the v1-Mongo sync until cutover)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import asyncpg


def _js(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


class OrbRepository:

    @staticmethod
    async def latest_universe(conn: asyncpg.Connection, on_or_before: date) -> dict[str, Any] | None:
        r = await conn.fetchrow(
            """
            SELECT trade_date, size, min_turnover_cr::FLOAT AS min_turnover_cr, pool, members, synced_at
            FROM orb.universe
            WHERE trade_date <= $1
            ORDER BY trade_date DESC
            LIMIT 1
            """,
            on_or_before,
        )
        if r is None:
            return None
        return {**dict(r), "pool": _js(r["pool"]), "members": _js(r["members"]) or []}

    @staticmethod
    async def latest_signal_date(conn: asyncpg.Connection, on_or_before: date) -> date | None:
        return await conn.fetchval(
            "SELECT max(trade_date) FROM orb.signals WHERE trade_date <= $1", on_or_before
        )

    @staticmethod
    async def signals_for(
        conn: asyncpg.Connection, trade_date: date, kind: str | None
    ) -> list[dict[str, Any]]:
        rows = await conn.fetch(
            """
            SELECT kind, sym, minute, side, entry_paise, stop_paise, t1_paise, t2_paise,
                   qty, risk_paise, candidates, passed, shortlist, screen_rows, config, at
            FROM orb.signals
            WHERE trade_date = $1 AND ($2::TEXT IS NULL OR kind = $2)
            ORDER BY kind, minute NULLS FIRST, sym
            """,
            trade_date,
            kind,
        )
        return [
            {**dict(r), "shortlist": _js(r["shortlist"]), "screen_rows": _js(r["screen_rows"])}
            for r in rows
        ]

    @staticmethod
    async def health_since(conn: asyncpg.Connection, since: date) -> list[dict[str, Any]]:
        rows = await conn.fetch(
            """
            SELECT trade_date, kind, agree_pct::FLOAT AS agree_pct, passes_exit_test, symbols,
                   minutes_compared, minutes_matched, at, extra
            FROM orb.health
            WHERE trade_date >= $1
            ORDER BY trade_date DESC, kind
            """,
            since,
        )
        return [{**dict(r), "extra": _js(r["extra"]) or {}} for r in rows]

    @staticmethod
    async def jobs_since(conn: asyncpg.Connection, since: date) -> list[dict[str, Any]]:
        rows = await conn.fetch(
            """
            SELECT trade_date, job, ok, minute, detail, seconds::FLOAT AS seconds, at
            FROM orb.jobs
            WHERE trade_date >= $1 AND job IS NOT NULL
            ORDER BY trade_date DESC, minute DESC NULLS LAST
            LIMIT 200
            """,
            since,
        )
        return [dict(r) for r in rows]

    @staticmethod
    async def journal_since(conn: asyncpg.Connection, since: date) -> list[dict[str, Any]]:
        rows = await conn.fetch(
            """
            SELECT trade_date, sym, reason, side, minute, qty, price_paise, entry_paise,
                   stop_paise, r::FLOAT AS r, config
            FROM orb.journal
            WHERE trade_date >= $1
            ORDER BY trade_date, minute NULLS LAST, id
            """,
            since,
        )
        return [dict(r) for r in rows]

    @staticmethod
    async def last_synced_at(conn: asyncpg.Connection) -> Any:
        return await conn.fetchval(
            """
            SELECT max(t) FROM (
                SELECT max(synced_at) AS t FROM orb.universe
                UNION ALL SELECT max(synced_at) FROM orb.signals
                UNION ALL SELECT max(synced_at) FROM orb.health
                UNION ALL SELECT max(synced_at) FROM orb.jobs
                UNION ALL SELECT max(synced_at) FROM orb.journal
            ) s
            """
        )
