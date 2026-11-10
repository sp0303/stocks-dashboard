"""Assemble the holdings heatmap from stored positions and closes (no provider calls, §3.2).

Day mode: one tile per held stock, its close-to-close move on a day (default: the latest
day most holdings have a close for; v2 has no live quotes on the request path).
Range mode: per-period moves from each stock's tracking day (its oldest open lot).
Returns are decimals (R12). This is the stock's move, not the client's P&L.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

import asyncpg
from pi_core import heatmap as hm

from pi_api.modules.heatmap.repository import HeatmapRepository

DAY_LOOKBACK = (
    20  # calendar days fetched before a day, to find the previous session's close
)
_EXCHANGE_PREF = {"NSE": 0, "BSE": 1}


def pick_series(
    rows: list[dict],
) -> tuple[dict[str, list[tuple[str, float]]], dict[str, str]]:
    """One exchange per symbol: the one with the most bars, NSE on a tie. Mixing exchanges
    day to day would turn the gap between their closes into fake moves."""
    by: dict[str, dict[str, list[tuple[str, float]]]] = {}
    for r in rows:
        by.setdefault(r["symbol"], {}).setdefault(r["exchange"], []).append(
            (r["price_date"].isoformat(), r["close"])
        )
    series, used = {}, {}
    for sym, exs in by.items():
        ex = min(exs, key=lambda e: (-len(exs[e]), _EXCHANGE_PREF.get(e, 9), e))
        series[sym], used[sym] = exs[ex], ex
    return series, used


class HeatmapService:
    def __init__(self, repo: HeatmapRepository | None = None) -> None:
        self.repo = repo or HeatmapRepository()

    async def _series(self, conn, symbols: list[str], since: date, until: date):
        rows = await self.repo.closes(conn, symbols, since, until)
        raw, used = pick_series(rows)
        acts: dict[str, list[dict]] = {}
        for a in await self.repo.actions(conn, symbols, since):
            acts.setdefault(a["symbol"], []).append(
                {**a, "ex_date": a["ex_date"].isoformat()}
            )
        return {
            s: hm.adjusted_closes(p, acts.get(s)) for s, p in raw.items() if p
        }, used

    async def build(
        self,
        conn: asyncpg.Connection,
        manager_id: UUID,
        client_ids: list[UUID] | None,
        mode: str,
        day: date | None,
        start: date | None,
        grain: str,
        today: date,
    ) -> dict:
        meta = {
            h["symbol"]: h
            for h in await self.repo.holdings(conn, manager_id, client_ids)
        }
        if not meta:
            return {
                "mode": mode,
                "tiles": [],
                "columns": [],
                "rows": [],
                "no_history": [],
            }
        for m in meta.values():
            m["entry_date"] = m["entry_date"].isoformat() if m["entry_date"] else None
        if mode == "day":
            return await self._day(conn, meta, day, today)
        return await self._range(conn, meta, start, grain, today)

    async def _day(self, conn, meta: dict, day: date | None, today: date) -> dict:
        until = day or today
        series, used = await self._series(
            conn, list(meta), until - timedelta(days=DAY_LOOKBACK), until
        )
        latest = hm.common_latest(series)
        target = day.isoformat() if day else latest
        rets = hm.day_returns(series, target) if target else {}
        tiles = [
            {**meta[s], **rets.get(s, {"ret": None}), "exchange": used.get(s)}
            for s in meta
        ]
        tiles.sort(key=lambda t: (t.get("ret") is None, -(t.get("ret") or 0)))
        return {
            "mode": "day",
            "day": target,
            "latest": latest,
            "tiles": tiles,
            "no_history": sorted(set(meta) - set(series)),
        }

    async def _range(
        self, conn, meta: dict, start: date | None, grain: str, today: date
    ) -> dict:
        starts = {
            s: (start.isoformat() if start else m["entry_date"])
            for s, m in meta.items()
        }
        first = min(filter(None, starts.values()), default=today.isoformat())
        series, used = await self._series(
            conn, list(meta), date.fromisoformat(first), today
        )
        end = hm.common_latest(series) or today.isoformat()
        g = hm.pick_grain(first, end) if grain == "auto" else grain
        m = hm.range_matrix(series, starts, end, g)
        for r in m["rows"]:
            r.update(
                {k: v for k, v in meta[r["symbol"]].items() if k != "symbol"},
                exchange=used.get(r["symbol"]),
            )
        m["rows"].sort(key=lambda r: -(r.get("invested") or 0))
        return {
            "mode": "range",
            "end": end,
            "no_history": sorted(set(meta) - set(series)),
            **m,
        }
