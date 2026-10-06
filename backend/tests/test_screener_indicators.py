"""Indicator lab: each indicator behaves sensibly on synthetic series."""
from datetime import date, timedelta

from app.services import screener_indicators as I


def _rows(closes, vols=None, spread=0.01):
    d0, out, k = date(2024, 1, 1), [], 0
    for i, c in enumerate(closes):
        while (d0 + timedelta(days=k)).weekday() >= 5:
            k += 1
        p = int(c * 100)
        out.append({"date": (d0 + timedelta(days=k)).isoformat(), "o": p, "h": int(p * (1 + spread)),
                    "l": int(p * (1 - spread)), "c": p, "v": (vols[i] if vols else 1000)})
        k += 1
    return out


UP = _rows([100 + i for i in range(200)])
DOWN = _rows([300 - i for i in range(200)])


def test_trend_indicators_have_the_right_sign():
    assert I.macd_hist(UP) is not None
    assert I.supertrend_dist(UP) > 0 > I.supertrend_dist(DOWN)
    assert I.donchian_pos(UP) > 0.95 and I.donchian_pos(DOWN) < 0.05
    assert I.adx(UP) > 25                      # strong steady trend
    assert I.bollinger_pctb(UP) > 0.8 and I.bollinger_pctb(DOWN) < 0.2


def test_obv_and_volume_surge():
    vols = [1000] * 195 + [5000] * 5
    r = _rows([100 + i for i in range(200)], vols)
    assert I.volume_surge(r) > 1.3
    assert I.obv_slope(UP) > 0 > I.obv_slope(DOWN)


def test_fibonacci_retracement_depth():
    # rally 100 -> 200 then pull back to 150 (50% of the swing)
    closes = [100 + i * (100 / 40) for i in range(41)] + [200 - i * (50 / 19) for i in range(1, 20)]
    r = _rows(closes, spread=0.0)
    v = I.fib_retracement(r, lookback=60)
    assert 0.45 < v < 0.55 and I.fib_in_zone(r, lookback=60) == 1.0


def test_short_history_returns_none():
    short = UP[:10]
    assert all(f(short) is None for f in I.INDICATORS.values())
