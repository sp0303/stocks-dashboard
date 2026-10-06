"""The live screen ranks by the validated Phase-1 composite, not the retired 1-week score.

Regression for the shipped `score_for()` (75% one-week momentum, anti-predictive): a stock
that just spiked last week must NOT outrank a steady 6-month leader near its 52-week high.
"""
from datetime import date, timedelta

from app.services import screener_daily


def _series(closes):
    d0 = date(2025, 1, 1)
    rows, day = [], 0
    for c in closes:
        while (d0 + timedelta(days=day)).weekday() >= 5:
            day += 1
        p = int(c * 100)
        rows.append({"date": (d0 + timedelta(days=day)).isoformat(),
                     "o": p, "h": int(p * 1.01), "l": int(p * 0.99), "c": p, "v": 100000})
        day += 1
    return rows


def _universe():
    n = 300
    steady = [100 * (1 + 0.6 * i / n) for i in range(n)]                 # +60%, at its high
    spiker = [100.0] * (n - 6) + [100, 104, 109, 115, 121, 128]           # flat, then +28% in a week
    faller = [100 * (1 - 0.3 * i / n) for i in range(n)]
    flats = {f"FLAT{i}": [100 + (i % 5) * 0.1] * n for i in range(12)}
    return {"STEADY": steady, "SPIKER": spiker, "FALLER": faller, **flats}


def test_compute_ranks_by_composite(monkeypatch):
    uni = {tk: _series(c) for tk, c in _universe().items()}
    kpis = {tk: {"name": tk, "industry": "Test"} for tk in uni}

    class Coll:
        def find(self, q, proj):
            return [{"_id": tk, "rows": uni[tk]} for tk in q["_id"]["$in"] if tk in uni]

    monkeypatch.setattr(screener_daily, "_load_kpis", lambda: kpis)
    monkeypatch.setattr(screener_daily, "_mongo", lambda: {screener_daily.DAILY_COLL: Coll()})
    monkeypatch.setattr(screener_daily.screener_fundamentals, "score_universe", lambda k: {})
    monkeypatch.setattr(screener_daily, "score_for",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("retired score used")))

    out = screener_daily.compute()
    rank = {s["ticker"]: s["rank"] for s in out["stocks"]}
    assert rank["STEADY"] < rank["SPIKER"]          # the old score put SPIKER first
    assert rank["STEADY"] == 1
    assert rank["FALLER"] == len(rank)
    assert out["data_as_of"] == uni["STEADY"][-1]["date"]
