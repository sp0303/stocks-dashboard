"""Market context for the swing screen: regime, F&O expiry phase, per-stock event badges.

Evidence (5-year point-in-time study, Oct 2022 – Oct 2026, outputs/rotation_* and lab3):
  * The composite's edge exists only when NIFTY is above its 50- and 200-day averages with
    broad participation (≥60% of stocks above their own 50-DMA); below the 200-DMA, or in
    high-volatility rebounds (India VIX ≥ 18), momentum leaders lag the market.
  * Entries at T-4 / T-3 sessions before the monthly F&O expiry, held ~10 sessions, beat
    entries at any other point of the month (the hold carries through the weak pre-expiry
    days into the post-expiry bounce).
  * Results and ex-dates move single stocks (results day averages ±3.8%; stocks drift down
    after results; run-ups precede buybacks and splits) but as hard filters they did not
    improve the strategy — so they are shown as badges, not used to exclude.
Pure functions only: inputs are plain lists/dicts, `today` is a parameter.
"""
from __future__ import annotations

from bisect import bisect_left
from datetime import date

BREADTH_ON = 0.60
VIX_OFF = 18.0
SIZE = {"on": 1.0, "caution": 0.5, "off": 0.0}
EVENT_HORIZON = 14          # sessions — the longest planned swing hold


def _dma(values: list[float], n: int) -> float | None:
    return sum(values[-n:]) / n if len(values) >= n else None


def regime(index_closes: list[float], breadth: float | None, vix: float | None) -> dict:
    """'on' | 'caution' | 'off' from the index trend, breadth and volatility (see module doc)."""
    last = index_closes[-1] if index_closes else None
    d50, d200 = _dma(index_closes, 50), _dma(index_closes, 200)
    reasons = []
    if last is None or d200 is None:
        state = "caution"
        reasons.append("not enough index history")
    elif last < d200:
        state = "off"
        reasons.append("NIFTY below its 200-day average")
    elif vix is not None and vix >= VIX_OFF:
        state = "off"
        reasons.append(f"India VIX {vix:.1f} ≥ {VIX_OFF:g}: momentum leaders tend to lag in volatile rebounds")
    elif d50 is not None and last > d50 and breadth is not None and breadth >= BREADTH_ON:
        state = "on"
        reasons.append("NIFTY above its 50- and 200-day averages with broad participation")
    else:
        state = "caution"
        if d50 is not None and last <= d50:
            reasons.append("NIFTY below its 50-day average")
        if breadth is None or breadth < BREADTH_ON:
            reasons.append("narrow participation")
    return {
        "state": state, "size_multiplier": SIZE[state], "reasons": reasons,
        "index_close": last, "dma50": d50, "dma200": d200,
        "breadth": breadth, "vix": vix,
    }


def expiry_phase(trading_dates: list[str], expiries: list[str], today: str) -> dict:
    """Where `today` sits in the monthly expiry cycle, in trading sessions.

    `trading_dates` must extend past today only if the calendar is known; future sessions
    are counted from weekdays when it does not (holidays then make the count an upper bound).
    """
    nxt = next((e for e in sorted(expiries) if e >= today), None)
    if nxt is None:
        return {"next_expiry": None, "sessions_to_expiry": None, "phase": "unknown"}
    i = bisect_left(trading_dates, today)
    if nxt in trading_dates:
        n = trading_dates.index(nxt) - i
    else:
        d0, d1 = date.fromisoformat(today), date.fromisoformat(nxt)
        n = sum(1 for k in range((d1 - d0).days)
                if date.fromordinal(d0.toordinal() + k + 1).weekday() < 5)
    phase = ("expiry day" if n == 0 else
             "entry window (T-4/T-3)" if n in (3, 4) else
             "pre-expiry (T-2/T-1)" if n in (1, 2) else
             "early cycle" if n > 4 else "unknown")
    return {"next_expiry": nxt, "sessions_to_expiry": n, "phase": phase,
            "in_entry_window": n in (3, 4)}


def event_badges(today: str, horizon_end: str, results: list[str],
                 actions: list[tuple[str, str, float | None]]) -> list[dict]:
    """Upcoming results / ex-dates for one stock in (today, horizon_end]. `actions` are
    (ex_date, type, amount_per_share). Also flags results within the last 5 sessions, since
    stocks tended to drift down after results."""
    out = []
    for d in sorted(results):
        if today < d <= horizon_end:
            out.append({"kind": "RESULTS", "date": d})
    for d, typ, amt in sorted(actions):
        if today < d <= horizon_end and typ in ("DIVIDEND", "BONUS", "SPLIT", "RIGHTS", "BUYBACK", "DEMERGER"):
            out.append({"kind": typ, "date": d, **({"amount": amt} if amt else {})})
    return out
