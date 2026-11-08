"""ORB service: shapes orb.* rows for the UI. Display only — no strategy logic lives here.

v1 stores prices as integer paise and agreement as a percentage; this layer converts to
rupees and decimal ratios (R12) so the UI formatters are the only place that scales.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg
from pi_api.modules.orb.repository import OrbRepository

IST = ZoneInfo("Asia/Kolkata")
EXIT_TEST_SESSIONS = 5
EXIT_TEST_MIN_AGREE = 0.995  # v1 recon.exit_test: 99.5 % minute agreement


def today_ist() -> date:
    return datetime.now(IST).date()


def rupees(paise: int | None) -> float | None:
    return None if paise is None else round(paise / 100.0, 2)


def hhmm(minute: int | None) -> str | None:
    return None if minute is None else f"{minute // 60:02d}:{minute % 60:02d}"


def side_label(side: int | None) -> str | None:
    if side is None or side == 0:
        return None
    return "LONG" if side > 0 else "SHORT"


def pct_to_ratio(v: float | None) -> float | None:
    return None if v is None else v / 100.0


def screen_row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "sym": r.get("sym"), "passed": bool(r.get("passed")), "failed": r.get("failed"),
        "or_high": rupees(r.get("or_high")), "or_low": rupees(r.get("or_low")),
        "or_width": pct_to_ratio(r.get("or_width_pct")),
        "rvol": r.get("rvol"), "turnover_cr": r.get("turnover_cr"),
    }


def entry_view(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "sym": r["sym"], "minute": r["minute"], "time": hhmm(r["minute"]),
        "side": side_label(r["side"]), "entry": rupees(r["entry_paise"]),
        "stop": rupees(r["stop_paise"]), "t1": rupees(r["t1_paise"]), "t2": rupees(r["t2_paise"]),
        "qty": r["qty"], "risk": rupees(r["risk_paise"]), "config": r["config"], "at": r["at"],
    }


def exit_test(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """Five most recent scored reconciliation sessions, all at or above 99.5 %."""
    scored = [s for s in sessions if s.get("agree_ratio") is not None][:EXIT_TEST_SESSIONS]
    passing = [s for s in scored if s["agree_ratio"] >= EXIT_TEST_MIN_AGREE]
    return {
        "sessions_required": EXIT_TEST_SESSIONS, "sessions_scored": len(scored),
        "sessions_passing": len(passing),
        "worst_agree_ratio": min((s["agree_ratio"] for s in scored), default=None),
        "passed": len(scored) >= EXIT_TEST_SESSIONS and len(passing) == len(scored),
    }


def journal_view(trades: list[dict[str, Any]], since: date) -> dict[str, Any]:
    out, run = [], 0.0
    for t in trades:
        r = t["r"] or 0.0
        run += r
        out.append({
            "trade_date": t["trade_date"], "sym": t["sym"], "reason": t["reason"],
            "side": side_label(t["side"]), "time": hhmm(t["minute"]), "qty": t["qty"],
            "price": rupees(t["price_paise"]), "entry": rupees(t["entry_paise"]),
            "stop": rupees(t["stop_paise"]), "r": t["r"], "cum_r": round(run, 3),
        })
    n = len(out)
    wins = sum(1 for t in trades if (t["r"] or 0) > 0)
    return {
        "since": since, "count": n, "total_r": round(run, 3),
        "win_rate": (wins / n) if n else None, "expectancy_r": round(run / n, 3) if n else None,
        "trades": out,
    }


class OrbService:

    def __init__(self, repo: OrbRepository = OrbRepository()) -> None:
        self.repo = repo

    async def universe(self, conn: asyncpg.Connection, on: date) -> dict[str, Any]:
        doc = await self.repo.latest_universe(conn, on)
        if doc is None:
            return {"members": []}
        doc["sector_mapped"] = sum(1 for m in doc["members"] if isinstance(m, dict) and m.get("sector_index"))
        return doc

    async def signals(self, conn: asyncpg.Connection, on: date | None, kind: str | None) -> dict[str, Any]:
        target = on or await self.repo.latest_signal_date(conn, today_ist())
        if target is None:
            return {"trade_date": None, "screen": None, "entries": []}
        rows = await self.repo.signals_for(conn, target, kind)
        screen = next((r for r in rows if r["kind"] == "screen"), None)
        entries = [entry_view(r) for r in rows if r["kind"] == "entry"]
        return {"trade_date": target, "entries": entries, "screen": None if screen is None else {
            "candidates": screen["candidates"], "passed": screen["passed"],
            "shortlist": screen["shortlist"] or [], "config": screen["config"], "at": screen["at"],
            "rows": sorted((screen_row(r) for r in (screen["screen_rows"] or [])),
                           key=lambda r: (not r["passed"], -(r["rvol"] or 0))),
        }}

    async def health(self, conn: asyncpg.Connection, days: int) -> dict[str, Any]:
        since = today_ist() - timedelta(days=days)
        rows = await self.repo.health_since(conn, since)
        sessions = [{**r, "agree_ratio": pct_to_ratio(r["agree_pct"])} for r in rows if r["kind"] == "reconcile"]
        beat = next((r for r in rows if r["kind"] == "heartbeat"), None)
        heartbeat = None if beat is None else {
            "trade_date": beat["trade_date"], "minute": beat["extra"].get("minute"),
            "time": hhmm(beat["extra"].get("minute")), "market_open": beat["extra"].get("market_open"),
            "at": beat["at"],
        }
        return {
            "last_synced_at": await self.repo.last_synced_at(conn), "sessions": sessions,
            "exit_test": exit_test(sessions), "heartbeat": heartbeat,
            "jobs": await self.repo.jobs_since(conn, since),
        }

    async def journal(self, conn: asyncpg.Connection, days: int) -> dict[str, Any]:
        since = today_ist() - timedelta(days=days)
        return journal_view(await self.repo.journal_since(conn, since), since)
