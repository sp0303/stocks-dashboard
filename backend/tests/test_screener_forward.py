"""Phase 5 forward-performance loop. Pins the outcome maths (returns, MFE/MAE, first-touch),
the maturity guard on outcome recording, and the realized IC / expectancy report. Pure — a
tiny in-memory fake stands in for Mongo."""
from app.services import screener_forward as FW


def rows(seq):
    """daily docs (paise) from (close, high, low) tuples."""
    return [{"c": int(c * 100), "h": int(h * 100), "l": int(l * 100)} for c, h, l in seq]


def test_forward_returns_by_horizon():
    closes = [102, 104, 101, 110]           # +1..+4 sessions after entry 100
    fr = FW.forward_returns(closes, 100.0, horizons=(1, 3, 4))
    assert fr[1] == 2.0 and fr[3] == 1.0 and fr[4] == 10.0
    assert 2 not in fr                       # horizon not requested


def test_mfe_mae():
    fut = rows([(101, 105, 99), (103, 108, 102)])
    mfe, mae = FW.mfe_mae(fut, 100.0, horizon=2)
    assert mfe == 8.0 and mae == -1.0


def test_first_touch_stop_target_time():
    entry, stop, target = 100.0, 95.0, 110.0
    assert FW.first_touch(rows([(97, 105, 96), (94, 100, 93)]), entry, stop, target, 5) == ("stop", 2)
    assert FW.first_touch(rows([(108, 111, 104)]), entry, stop, target, 5) == ("target", 1)
    assert FW.first_touch(rows([(100, 102, 98)] * 3), entry, stop, target, 3)[0] == "time"


def test_record_outcomes_waits_for_maturity():
    snap = {"as_of": "2025-01-01", "stocks": [
        {"ticker": "A", "setup": "Pullback setup", "score": 1.0, "entry": 100.0,
         "stop": 95.0, "t2": 110.0, "risk_per_share": 5.0}]}
    short = rows([(101, 102, 99)] * 3)       # fewer than max horizon (20)
    FW.record_outcomes(dict(snap), lambda tk, d: short)
    out = FW.record_outcomes({**snap, "stocks": [dict(snap["stocks"][0])]},
                             lambda tk, d: short)
    assert out["matured"] == 0               # too little forward data → not recorded

    long = rows([(100 + i * 0.6, 100 + i * 0.6 + 1, 100 + i * 0.6 - 1) for i in range(22)])
    out2 = FW.record_outcomes({**snap, "stocks": [dict(snap["stocks"][0])]},
                              lambda tk, d: long)
    assert out2["matured"] == 1
    oc = out2["stocks"][0]["outcomes"]
    assert "ret_net" in oc and oc["first_touch"] in ("stop", "target", "time")
    assert oc["r_net"] is not None


def test_realized_report_ic_positive_when_score_predicts():
    # 10 names: higher score → higher net forward return → IC should be strongly positive.
    stocks = [{"ticker": f"S{i}", "setup": "No setup", "score": float(i),
               "outcomes": {"ret_net": {10: float(i)}}} for i in range(10)]
    rep = FW.realized_report([{"as_of": "2025-01-01", "stocks": stocks}], horizon=10)
    assert rep["pooled_realized_ic"] > 0.9
    assert rep["pairs"] == 10


def test_realized_report_setup_expectancy():
    stocks = [
        {"ticker": "A", "setup": "Pullback setup", "score": 1.0,
         "outcomes": {"ret_net": {10: 2.0}, "r_net": 0.5}},
        {"ticker": "B", "setup": "Pullback setup", "score": 2.0,
         "outcomes": {"ret_net": {10: 3.0}, "r_net": 1.5}},
    ]
    rep = FW.realized_report([{"as_of": "2025-02-01", "stocks": stocks}])
    assert rep["setup_expectancy_r"]["Pullback setup"]["n"] == 2
    assert rep["setup_expectancy_r"]["Pullback setup"]["exp_r"] == 1.0


class _FakeColl:
    def __init__(self):
        self.docs = {}

    def replace_one(self, flt, doc, upsert=False):
        self.docs[flt["_id"]] = doc

    def find(self):
        store = self

        class _Cur:
            def __init__(self):
                self._items = list(store.docs.values())

            def sort(self, *a):
                self._items.sort(key=lambda d: d["_id"], reverse=True)
                return self

            def limit(self, n):
                return self._items[:n]
        return _Cur()


class _FakeDB:
    def __init__(self):
        self._c = _FakeColl()

    def __getitem__(self, name):
        return self._c


def test_save_is_idempotent_per_date():
    db = _FakeDB()
    FW.save_snapshot(db, {"_id": "2025-03-01", "as_of": "2025-03-01", "stocks": []})
    FW.save_snapshot(db, {"_id": "2025-03-01", "as_of": "2025-03-01", "stocks": [{"x": 1}]})
    snaps = FW.load_snapshots(db)
    assert len(snaps) == 1 and snaps[0]["stocks"] == [{"x": 1}]     # overwrote, not duplicated
