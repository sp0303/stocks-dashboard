"""Market context: regime states, expiry phase counting, event badges."""
from app.services import screener_market as M


def _trend(start, step, n=220):
    return [start + step * i for i in range(n)]


def test_regime_on_off_caution():
    up = _trend(100, 0.5)
    assert M.regime(up, 0.7, 13.0)["state"] == "on"
    assert M.regime(up, 0.7, 13.0)["size_multiplier"] == 1.0
    assert M.regime(up, 0.45, 13.0)["state"] == "caution"          # narrow breadth
    assert M.regime(up, 0.7, 19.5)["state"] == "off"               # volatile rebound risk
    down = _trend(200, -0.5)
    r = M.regime(down, 0.8, 12.0)
    assert r["state"] == "off" and "200-day" in r["reasons"][0]
    assert M.regime(up[:100], 0.7, 12.0)["state"] == "caution"     # not enough history


def test_expiry_phase_counts_sessions_and_flags_window():
    days = ["2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23", "2026-10-26", "2026-10-27"]
    exp = ["2026-09-29", "2026-10-27", "2026-11-24"]
    p = M.expiry_phase(days, exp, "2026-10-21")
    assert p["next_expiry"] == "2026-10-27" and p["sessions_to_expiry"] == 4 and p["in_entry_window"]
    assert M.expiry_phase(days, exp, "2026-10-27")["phase"] == "expiry day"
    # calendar not known that far: count weekdays
    far = M.expiry_phase(days[:1], exp, "2026-10-20")
    assert far["sessions_to_expiry"] == 5 and far["phase"] == "early cycle"


def test_event_badges_window():
    b = M.event_badges("2026-10-06", "2026-10-26",
                       results=["2026-07-20", "2026-10-15"],
                       actions=[("2026-10-09", "DIVIDEND", 5.0), ("2026-11-02", "SPLIT", None),
                                ("2026-10-12", "OTHER", None)])
    assert [x["kind"] for x in b] == ["RESULTS", "DIVIDEND"]
    assert b[1]["amount"] == 5.0


# ── integration: compute()'s _market_context against a fake Mongo ──
from datetime import date as _date, timedelta as _td

from app.services import screener_daily as SD


class _Coll:
    def __init__(self, docs):
        self.docs = docs

    @staticmethod
    def _match(doc, q):
        for k, cond in q.items():
            v = doc.get(k)
            if isinstance(cond, dict):
                if "$in" in cond and v not in cond["$in"]:
                    return False
                if "$gt" in cond and not (v is not None and v > cond["$gt"]):
                    return False
                if "$lte" in cond and not (v is not None and v <= cond["$lte"]):
                    return False
            elif v != cond:
                return False
        return True

    def find(self, q=None, proj=None):
        return [d for d in self.docs if self._match(d, q or {})]

    def find_one(self, q, proj=None):
        r = self.find(q)
        return r[0] if r else None


def _days(n, end="2026-10-06"):
    out, d = [], _date.fromisoformat(end)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= _td(days=1)
    return out[::-1]


def test_market_context_end_to_end_without_official_calendar():
    ds = _days(230)
    idx = [{"date": d, "c": int((100 + i * 0.3) * 100)} for i, d in enumerate(ds)]
    db = {
        SD.DAILY_COLL: _Coll([{"_id": "NIFTYBEES", "rows": idx},
                              {"_id": "INDIA VIX", "rows": [{"date": ds[-1], "c": 1250}]}]),
        "market_fno_expiries": _Coll([]),
        "market_results_calendar": _Coll([{"symbol": "AAA", "meeting_date": "2026-10-15"}]),
        "market_corporate_actions": _Coll([{"symbol": "HEGAM", "ex_date": "2026-10-09",
                                            "type": "DIVIDEND", "amount_per_share": 4.0}]),
    }
    metrics = {"AAA": {"price": 110, "dma50": 100}, "HEG": {"price": 90, "dma50": 100}, "BBB": {"price": 120, "dma50": 100}}
    stocks = [{"ticker": t} for t in metrics]
    ctx = SD._market_context(db, ds[-1], metrics, stocks)
    assert ctx["regime"]["state"] == "on" and abs(ctx["regime"]["breadth"] - 2 / 3) < 1e-9
    assert ctx["regime"]["vix"] == 12.5
    assert ctx["expiry"]["next_expiry"] == "2026-10-27"          # last Tuesday of Oct 2026
    assert ctx["expiry"]["sessions_to_expiry"] == 15
    ev = {s["ticker"]: s["events"] for s in stocks}
    assert ev["AAA"][0]["kind"] == "RESULTS"
    assert ev["HEG"][0]["kind"] == "DIVIDEND"                    # HEG → HEGAM alias
    assert ev["BBB"] == [] and ctx["events_window"]["stocks_with_events"] == 2
