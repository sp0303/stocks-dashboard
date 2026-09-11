"""ORB engine — read-only API.

Every endpoint degrades rather than 500s when the engine is off or MongoDB is not
configured: the /orb page's first job is to tell you *why* nothing is running, which it
cannot do if the status call itself fails.

Nothing here places an order or mutates a signal. The engine is paper-only, and the API
is a window onto it.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from app.config import settings
from app.services.orb import calendar as orb_calendar
from app.services.orb import engine as orb_engine
from app.services.orb import recon, signals, store
from app.services.orb.config import DEFAULT
from app.services.orb.session import MARKET_OPEN, hhmm, to_rupees, today_ist

router = APIRouter(prefix="/api/orb", tags=["orb"])


def _guard(fn, *a, **kw):
    """Run a synchronous store call, turning a missing database into a clean answer."""
    try:
        return fn(*a, **kw), None
    except store.StoreUnavailable as exc:
        return None, str(exc)


@router.get("/status")
async def status():
    """Is the engine alive, is it recording, and has it earned the right to trade yet."""
    def _build():
        eng = orb_engine.get_engine()
        data, err = _guard(store.status)
        out = {
            "enabled": settings.orb_enabled,
            "strategy_enabled": settings.orb_strategy_enabled,
            "running": eng is not None,
            "start_error": orb_engine.start_error(),
            "store": data or {"connected": False, "error": err},
            "config_version": DEFAULT.version,
            "today": today_ist().isoformat(),
        }
        if eng is not None:
            out["engine"] = eng.status()
        else:
            health, _ = _guard(recon.exit_test)
            out["exit_test"] = health
        return out

    return {"data": await run_in_threadpool(_build)}


@router.get("/universe")
async def universe():
    def _build():
        rows, err = _guard(store.find, store.UNIVERSE, {}, [("date", -1)], 1)
        if err:
            return {"error": err, "members": []}
        if not rows:
            return {"members": [], "note": "run scripts/orb_backfill.py universe"}
        doc = rows[0]
        mapped = sum(1 for m in doc["members"] if m.get("sector_index"))
        return {"date": doc["date"], "size": doc["size"], "pool": doc.get("pool"),
                "min_turnover_cr": doc.get("min_turnover_cr"),
                "sector_mapped": mapped, "members": doc["members"]}

    return {"data": await run_in_threadpool(_build)}


@router.get("/day")
async def day(d: str | None = Query(None, alias="date")):
    """Everything the live page needs in one call: the screen with every candidate's
    pass/fail trace, the day's signals, and the calendar entry."""
    target = d or today_ist().isoformat()

    def _build():
        screen, err = _guard(store.get, store.SIGNALS, f"{target}:screen")
        if err:
            return {"error": err}
        entries, _ = _guard(store.find, store.SIGNALS,
                            {"date": target, "kind": "entry"}, [("minute", 1)])
        trades, _ = _guard(store.find, store.JOURNAL, {"date": target}, [("minute", 1)])
        cal, _ = _guard(orb_calendar.entry, target)
        rows = (screen or {}).get("rows", [])
        return {
            "date": target,
            "calendar": cal,
            "screened": len(rows),
            "passed": (screen or {}).get("passed", 0),
            "shortlist": (screen or {}).get("shortlist", []),
            "candidates": sorted(rows, key=lambda r: (not r["passed"],
                                                      -(r.get("rvol") or 0))),
            "signals": [_signal_view(e) for e in (entries or [])],
            "trades": trades or [],
            "summary": signals.day_summary(target) if trades else None,
        }

    return {"data": await run_in_threadpool(_build)}


def _signal_view(e: dict) -> dict:
    return {
        "sym": e["sym"], "minute": e["minute"], "time": hhmm(e["minute"]),
        "side": "LONG" if e["side"] > 0 else "SHORT",
        "entry": to_rupees(e["entry"]), "stop": to_rupees(e["stop"]),
        "t1": to_rupees(e["t1"]), "t2": to_rupees(e["t2"]),
        "qty": e["qty"], "risk": to_rupees(e["risk"]),
        "trace": e.get("trace", []),
    }


@router.get("/chart/{symbol}")
async def chart(symbol: str, d: str | None = Query(None, alias="date")):
    """Bars, VWAP and the opening range for one symbol-day, shaped for the UI."""
    target = d or today_ist().isoformat()

    def _build():
        from app.services.orb.features import opening_range, vwap_series

        bars, err = _guard(store.load_session, symbol.upper(), target)
        if err:
            return {"error": err}
        if not bars:
            return {"symbol": symbol.upper(), "date": target, "bars": []}
        v = vwap_series(bars)
        vmap = dict(v.history)
        o = opening_range(bars)
        return {
            "symbol": symbol.upper(), "date": target,
            "or": {"high": to_rupees(o.high), "low": to_rupees(o.low),
                   "mid": to_rupees(o.mid), "width_pct": round(o.width_pct, 3)}
            if o else None,
            "bars": [{"t": hhmm(b.minute), "m": b.minute, "o": to_rupees(b.o),
                      "h": to_rupees(b.h), "l": to_rupees(b.l), "c": to_rupees(b.c),
                      "v": b.v, "syn": b.syn, "vwap": to_rupees(vmap.get(b.minute))}
                     for b in bars],
        }

    return {"data": await run_in_threadpool(_build)}


@router.get("/journal")
async def journal(days: int = Query(30, ge=1, le=365)):
    """Closed paper trades and the running result, in R."""
    since = (date.today() - timedelta(days=days)).isoformat()

    def _build():
        trades, err = _guard(store.find, store.JOURNAL, {"date": {"$gte": since}},
                             [("date", 1), ("minute", 1)])
        if err:
            return {"error": err, "trades": []}
        trades = trades or []
        curve, run = [], 0.0
        for t in trades:
            run += t.get("r", 0)
            curve.append({"date": t["date"], "sym": t["sym"], "r": round(t.get("r", 0), 3),
                          "cum_r": round(run, 3)})
        wins = [t for t in trades if t.get("r", 0) > 0]
        return {
            "from": since, "trades": trades, "curve": curve,
            "count": len(trades), "total_r": round(run, 2),
            "win_pct": round(len(wins) / len(trades) * 100, 1) if trades else None,
            "expectancy_r": round(run / len(trades), 3) if trades else None,
        }

    return {"data": await run_in_threadpool(_build)}


@router.get("/health")
async def health(days: int = Query(15, ge=1, le=90)):
    """Reconciliation history — the number that decides whether the strategy may run."""
    def _build():
        rows, err = _guard(recon.recent_health, days)
        if err:
            return {"error": err, "sessions": []}
        test, _ = _guard(recon.exit_test)
        return {"sessions": rows or [], "exit_test": test}

    return {"data": await run_in_threadpool(_build)}


@router.get("/calendar")
async def calendar(days: int = Query(60, ge=1, le=800)):
    def _build():
        end = date.today()
        start = end - timedelta(days=days)
        rows, err = _guard(store.find, store.CALENDAR,
                           {"date": {"$gte": start.isoformat(), "$lte": end.isoformat()}},
                           [("date", 1)])
        if err:
            return {"error": err, "days": []}
        return {"days": rows or [],
                "trading": sum(1 for r in (rows or []) if r.get("trading")),
                "half_days": [r["date"] for r in (rows or []) if r.get("half_day")]}

    return {"data": await run_in_threadpool(_build)}


@router.get("/config")
async def config():
    return {"data": {"version": DEFAULT.version, "values": DEFAULT.to_dict()}}
