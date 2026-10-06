"""Indicator lab — classic technical indicators as candidate factors (research only).

Nothing here is used by the live screen until it passes the gate in
scripts/indicator_lab.py: a positive, significant rank-IC *within the composite's top
100* in BOTH halves of the 5-year sample. Each function is pure: daily rows in
(the store shape {"date","o","h","l","c" paise,"v"}), one number out (None if the history
is too short). Values are oriented so that "higher = expected better" is NOT assumed —
the lab measures the sign; the direction is decided by the evidence.
"""
from __future__ import annotations


def _c(rows):
    return [r["c"] / 100 for r in rows]


def _ema(vals: list[float], n: int) -> list[float]:
    k, out = 2 / (n + 1), []
    for v in vals:
        out.append(v if not out else out[-1] + k * (v - out[-1]))
    return out


def _std(vals):
    m = sum(vals) / len(vals)
    return (sum((x - m) ** 2 for x in vals) / len(vals)) ** 0.5


def bollinger_pctb(rows, n=20, k=2.0):
    c = _c(rows)
    if len(c) < n:
        return None
    w = c[-n:]
    m, sd = sum(w) / n, _std(w)
    return (c[-1] - (m - k * sd)) / (2 * k * sd) if sd else None


def bollinger_squeeze(rows, n=20, lookback=120):
    """Today's band width relative to its own last-`lookback` range (0 = tightest)."""
    c = _c(rows)
    if len(c) < n + lookback:
        return None
    widths = []
    for i in range(len(c) - lookback, len(c) + 1):
        w = c[i - n:i]
        m = sum(w) / n
        widths.append(_std(w) / m if m else 0)
    lo, hi = min(widths), max(widths)
    return (widths[-1] - lo) / (hi - lo) if hi > lo else None


def macd_hist(rows):
    c = _c(rows)
    if len(c) < 60:
        return None
    m = [a - b for a, b in zip(_ema(c, 12), _ema(c, 26))]
    sig = _ema(m, 9)
    return (m[-1] - sig[-1]) / c[-1]


def _tr(rows, i):
    h, l, pc = rows[i]["h"], rows[i]["l"], rows[i - 1]["c"]
    return max(h - l, abs(h - pc), abs(l - pc))


def adx(rows, n=14):
    if len(rows) < 3 * n + 1:
        return None
    pdm, ndm, trs = [], [], []
    for i in range(1, len(rows)):
        up = rows[i]["h"] - rows[i - 1]["h"]
        dn = rows[i - 1]["l"] - rows[i]["l"]
        pdm.append(up if up > dn and up > 0 else 0)
        ndm.append(dn if dn > up and dn > 0 else 0)
        trs.append(_tr(rows, i))

    def wilder(x):
        s = [sum(x[:n])]
        for v in x[n:]:
            s.append(s[-1] - s[-1] / n + v)
        return s
    atr, p, m = wilder(trs), wilder(pdm), wilder(ndm)
    dx = []
    for a, b, t in zip(p, m, atr):
        pdi, ndi = (100 * a / t, 100 * b / t) if t else (0, 0)
        dx.append(100 * abs(pdi - ndi) / (pdi + ndi) if pdi + ndi else 0)
    if len(dx) < n:
        return None
    adx_ = sum(dx[:n]) / n
    for v in dx[n:]:
        adx_ = (adx_ * (n - 1) + v) / n
    return adx_


def supertrend_dist(rows, n=10, mult=3.0):
    """Distance of close above the Supertrend line, in ATRs (negative = below = downtrend)."""
    if len(rows) < n + 30:
        return None
    atr, line, trend = None, None, 1
    up_prev = dn_prev = None
    for i in range(1, len(rows)):
        tr = _tr(rows, i) / 100
        atr = tr if atr is None else (atr * (n - 1) + tr) / n
        hl2 = (rows[i]["h"] + rows[i]["l"]) / 200
        c = rows[i]["c"] / 100
        up, dn = hl2 - mult * atr, hl2 + mult * atr
        if up_prev is not None:
            up = max(up, up_prev) if rows[i - 1]["c"] / 100 > up_prev else up
            dn = min(dn, dn_prev) if rows[i - 1]["c"] / 100 < dn_prev else dn
        if trend == 1 and c < up:
            trend = -1
        elif trend == -1 and c > dn:
            trend = 1
        line = up if trend == 1 else dn
        up_prev, dn_prev = up, dn
    return (rows[-1]["c"] / 100 - line) / atr if atr else None


def donchian_pos(rows, n=55):
    """Close within the prior n-session range (1.0 = at/above the high → breakout)."""
    if len(rows) < n + 1:
        return None
    prior = rows[-n - 1:-1]
    hi, lo = max(r["h"] for r in prior), min(r["l"] for r in prior)
    return (rows[-1]["c"] - lo) / (hi - lo) if hi > lo else None


def obv_slope(rows, n=20):
    """OBV change over n sessions, scaled by average volume (accumulation vs distribution)."""
    if len(rows) < n + 2:
        return None
    obv, series = 0, []
    for i in range(1, len(rows)):
        v = rows[i].get("v") or 0
        obv += v if rows[i]["c"] > rows[i - 1]["c"] else -v if rows[i]["c"] < rows[i - 1]["c"] else 0
        series.append(obv)
    avg_v = sum((r.get("v") or 0) for r in rows[-n:]) / n
    return (series[-1] - series[-n - 1]) / (avg_v * n) if avg_v else None


def volume_surge(rows, short=5, long=50):
    if len(rows) < long:
        return None
    s = sum((r.get("v") or 0) for r in rows[-short:]) / short
    l = sum((r.get("v") or 0) for r in rows[-long:]) / long
    return s / l if l else None


def pivot_r1_dist(rows):
    """Distance to the prior calendar month's classic pivot R1, in % of price
    (negative = still below R1)."""
    if len(rows) < 45:
        return None
    this_m = rows[-1]["date"][:7]
    prev = [r for r in rows if r["date"][:7] < this_m]
    if not prev:
        return None
    pm = prev[-1]["date"][:7]
    pmr = [r for r in prev if r["date"][:7] == pm]
    h, l, c = max(r["h"] for r in pmr), min(r["l"] for r in pmr), pmr[-1]["c"]
    p = (h + l + c) / 3
    r1 = 2 * p - l
    return (rows[-1]["c"] - r1) / r1


def fib_retracement(rows, lookback=60):
    """How far price has retraced the last swing: 0 = at the swing high, 1 = back at the
    swing low (0.382–0.618 is the classic 'buy the pullback' zone)."""
    if len(rows) < lookback:
        return None
    w = rows[-lookback:]
    hi_i = max(range(len(w)), key=lambda i: w[i]["h"])
    if hi_i == 0:
        return None
    lo = min(r["l"] for r in w[:hi_i + 1])
    hi = w[hi_i]["h"]
    return (hi - w[-1]["c"]) / (hi - lo) if hi > lo else None


def fib_in_zone(rows, lookback=60):
    v = fib_retracement(rows, lookback)
    return None if v is None else (1.0 if 0.382 <= v <= 0.618 else 0.0)


INDICATORS = {
    "bb_pctb": bollinger_pctb,
    "bb_squeeze": bollinger_squeeze,
    "macd_hist": macd_hist,
    "adx": adx,
    "supertrend": supertrend_dist,
    "donchian55": donchian_pos,
    "obv_slope": obv_slope,
    "vol_surge": volume_surge,
    "pivot_r1": pivot_r1_dist,
    "fib_retrace": fib_retracement,
    "fib_zone": fib_in_zone,
}
