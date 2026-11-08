"""Synthetic v1 orb_* documents, shaped like v1's writers (store.put calls). No real data."""

from __future__ import annotations

from bson import ObjectId  # pymongo ships bson


def universe_doc() -> dict:
    return {"_id": "2026-10-01", "date": "2026-10-01", "size": 2, "min_turnover_cr": 25.5,
            "pool": 1800, "members": [{"sym": "AAA", "token": "1", "sector_index": "NIFTY IT"},
                                      {"sym": "BBB", "token": "2"}],
            "ranked": [{"sym": "AAA", "turnover_cr": 90.1}]}


def screen_doc() -> dict:
    return {"_id": "2026-10-01:screen", "date": "2026-10-01", "kind": "screen",
            "candidates": 2, "passed": 1, "shortlist": ["AAA"],
            "rows": [{"sym": "AAA", "passed": True, "failed": None, "or_high": 101050,
                      "or_low": 100000, "or_width_pct": 1.05, "rvol": 2.4, "turnover_cr": 12.3,
                      "trace": ["x"]},
                     {"sym": "BBB", "passed": False, "failed": "rule", "or_high": None,
                      "or_low": None, "or_width_pct": None, "rvol": float("nan"),
                      "turnover_cr": None, "trace": []}],
            "config": "v3", "at": "2026-10-01T09:31:02+05:30"}


def entry_doc() -> dict:
    return {"_id": "2026-10-01:AAA:575", "date": "2026-10-01", "sym": "AAA", "kind": "entry",
            "minute": 575, "side": 1, "entry": 101100, "stop": 100400, "t1": 102500,
            "t2": 103900, "qty": 14, "risk": 9800, "config": "v3", "trace": ["x"],
            "at": "2026-10-01T09:35:00+05:30"}


def health_docs() -> list[dict]:
    return [
        {"_id": "2026-10-01", "date": "2026-10-01", "symbols": 10, "minutes_compared": 3750,
         "minutes_matched": 3745, "agree_pct": 99.867, "repaired_symbols": 0, "failures": [],
         "worst": [], "passes_exit_test": True, "at": "2026-10-01T16:10:00+05:30"},
        {"_id": "2026-10-01:recorder", "date": "2026-10-01", "kind": "recorder", "ticks": 5},
        {"_id": "orb-heartbeat", "date": "2026-10-01", "minute": 600, "owner": "host:1",
         "market_open": True, "at": 1790000000.5, "recent": []},
    ]


def job_docs() -> list[dict]:
    return [
        {"_id": "2026-10-01:screen", "date": "2026-10-01", "job": "screen", "ok": True,
         "minute": 570, "detail": "1/2 passed", "seconds": 1.234, "owner": "host:1",
         "at": "2026-10-01T09:30:01+05:30"},
        {"_id": "orb-engine", "owner": "host:1", "expires_at": 1790000100.0},
    ]


def journal_doc() -> dict:
    return {"_id": ObjectId("65f000000000000000000001"), "date": "2026-10-01", "sym": "AAA",
            "reason": "t1", "price": 102500, "minute": 600, "qty": 7, "r": 0.714, "side": 1,
            "entry": 101100, "stop": 100400, "config": "v3", "at": "2026-10-01T10:00:00+05:30"}


def all_docs() -> dict[str, list[dict]]:
    return {"orb_universe": [universe_doc()], "orb_signals": [screen_doc(), entry_doc()],
            "orb_health": health_docs(), "orb_jobs": job_docs(), "orb_journal": [journal_doc()]}
