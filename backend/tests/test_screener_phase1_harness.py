"""Phase 1 harness wiring — proves the composite path runs end to end and that the four
execution-realism layers actually bite. Runs on synthetic data via a stubbed universe;
no Mongo, no network.
"""
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import screener_backtest as bt          # noqa: E402
import screener_phase1_backtest as p1   # noqa: E402


def _make(trend, adv_ok=True, wide=False, n=260, seed=0):
    rnd = random.Random(seed)
    rows, px = [], 100.0
    for i in range(n):
        px *= (1 + trend / n + rnd.uniform(-0.008, 0.008))
        spread = px * (0.03 if wide else 0.012)
        c = int(px * 100)
        rows.append({"date": f"2024-{1 + i // 22:02d}-{1 + i % 22:02d}",
                     "o": c, "h": int((px + spread / 2) * 100),
                     "l": int((px - spread / 2) * 100), "c": c,
                     "v": 500000 if adv_ok else 50})
    return rows


def _universe(**kw):
    uni = {}
    for k in range(60):
        uni[f"UP{k}"] = {"rows": _make(0.6, wide=(k % 3 == 0), seed=k)}
    for k in range(60):
        uni[f"DN{k}"] = {"rows": _make(-0.4, seed=100 + k)}
    uni["ILLIQ"] = {"rows": _make(0.9, adv_ok=False, seed=999)}   # strong trend, no liquidity
    for sym, v in uni.items():
        dates = [r["date"] for r in v["rows"]]
        v["dates"] = dates
        v["closes"] = [r["c"] / 100 for r in v["rows"]]
        v["idx"] = {d: i for i, d in enumerate(dates)}
        v["sector"] = "Test"
    return uni


@pytest.fixture(autouse=True)
def stub_universe(monkeypatch):
    monkeypatch.setattr(bt, "load_universe", _universe)


def test_composite_ranks_uptrends_above_downtrends_with_positive_ic():
    res = p1.run(every=10, cost_pct=0.30, min_adv=1_000_000, progress=False)
    import statistics
    for h in p1.HORIZONS:
        assert statistics.mean(res["dec"][h][10]) > statistics.mean(res["dec"][h][1])
        assert statistics.mean(res["ic"][h]) > 0


def test_costs_reduce_the_edge():
    free = p1.run(every=10, cost_pct=0.0, min_adv=0, progress=False)
    costly = p1.run(every=10, cost_pct=1.0, min_adv=0, progress=False)
    import statistics
    h = p1.HORIZONS[-1]
    assert statistics.mean(costly["edge_net"][h]) < statistics.mean(free["edge_net"][h])


def test_adv_floor_excludes_the_illiquid_name_before_scoring():
    # With the floor, ILLIQ can never appear; without it, its strong trend puts it in D10.
    with_floor = _run_capture(min_adv=1_000_000)
    no_floor = _run_capture(min_adv=0)
    assert "ILLIQ" not in with_floor
    assert "ILLIQ" in no_floor


def _run_capture(min_adv):
    """Re-run one rebalance and capture which symbols were scored, to check the floor."""
    uni = _universe()
    seen = set()
    orig = p1.F.Composite.score_universe

    def spy(self, raw_by):
        seen.update(raw_by)
        return orig(self, raw_by)

    p1.F.Composite.score_universe = spy
    try:
        bt.load_universe = lambda: uni
        p1.run(every=40, cost_pct=0, min_adv=min_adv, progress=False)
    finally:
        p1.F.Composite.score_universe = orig
    return seen


def test_regime_filter_changes_the_long_book_return():
    # A breadth gate of 101% is never satisfied -> long book always in cash -> regime
    # edge differs from the unfiltered net edge.
    res = p1.run(every=10, cost_pct=0.30, regime_breadth=101, progress=False)
    import statistics
    h = p1.HORIZONS[-1]
    assert res["regime"] and not any(res["regime"])          # every date forced risk-off
    assert (statistics.mean(res["edge_net_regime"][h])
            != statistics.mean(res["edge_net"][h]))
