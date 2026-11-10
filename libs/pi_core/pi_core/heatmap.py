"""Holdings heatmap: per-stock returns for one day, or period by period since tracking began.

Pure functions over daily closes so they test without a store (AGENTS §3.4). Same maths as
v1 ``app.services.heatmap``. Every return is a DECIMAL (0.0123 = +1.23 %); only the UI
formats it (R12). A stock's move is not the client's P&L, which depends on every buy price.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import date

Series = list[tuple[str, float]]  # (ISO date, close), sorted by date

# A split or bonus shows up in an as-traded close series as an overnight drop by the
# multiplier. Backward-adjust ONLY when the jump really is there (within this tolerance):
# some stored history is already adjusted, and dividing it again would invent a rally (R8/R17).
_JUMP_TOLERANCE = 0.25
# A daily move this large with no corporate action behind it is more likely bad data.
SUSPECT_MOVE = 0.40


def adjusted_closes(points: list[tuple[str, float]], actions: list[dict] | None = None) -> Series:
    """Sorted (date, close), with pre-ex-date closes divided by a split/bonus multiplier when
    the series shows that jump on the ex-date."""
    rows = sorted((str(d)[:10], float(c)) for d, c in points if c)
    if not rows:
        return []
    dates = [d for d, _ in rows]
    closes = [c for _, c in rows]
    for a in actions or []:
        mult = float(a.get("qty_multiplier") or 1.0)
        ex = str(a.get("ex_date") or "")[:10]
        if a.get("type") not in ("SPLIT", "BONUS") or mult == 1.0 or not ex:
            continue
        i = bisect_left(dates, ex)
        if i <= 0 or i >= len(dates):
            continue
        jump = closes[i - 1] / closes[i]
        if abs(jump / mult - 1.0) <= _JUMP_TOLERANCE:
            for j in range(i):
                closes[j] /= mult
    return list(zip(dates, closes))


def common_latest(series_by_sym: dict[str, Series]) -> str | None:
    """The last date most stocks share, not the newest single bar: one symbol with a stray
    late bar must not end every row there."""
    lasts = Counter(s[-1][0] for s in series_by_sym.values() if s)
    return max(lasts, key=lambda d: (lasts[d], d)) if lasts else None


def day_returns(series_by_sym: dict[str, Series], day: str) -> dict[str, dict]:
    """Close-to-close return ON ``day``. A stock with no bar that day gets ret None (it did
    not trade or the data is missing), never a carried-over 0."""
    out: dict[str, dict] = {}
    for sym, series in series_by_sym.items():
        i = bisect_left(series, (day, float("-inf")))
        has_bar = i < len(series) and series[i][0] == day
        if not has_bar or i == 0:
            out[sym] = {
                "ret": None,
                "close": series[i][1] if has_bar else None,
                "prev_close": None,
                "prev_date": None,
                "suspect": False,
            }
            continue
        prev, cur = series[i - 1][1], series[i][1]
        r = cur / prev - 1.0
        out[sym] = {
            "ret": r,
            "close": cur,
            "prev_close": prev,
            "prev_date": series[i - 1][0],
            "suspect": abs(r) >= SUSPECT_MOVE,
        }
    return out


def pick_grain(start: str, end: str) -> str:
    """Days for about two months, weeks up to about 18 months, months beyond."""
    span = (date.fromisoformat(end) - date.fromisoformat(start)).days
    if span <= 62:
        return "day"
    if span <= 550:
        return "week"
    return "month"


def period_of(day: str, grain: str) -> str:
    if grain == "day":
        return day
    if grain == "week":
        y, w, _ = date.fromisoformat(day).isocalendar()
        return f"{y}-W{w:02d}"
    return day[:7]


def _row(sym: str, window: Series, grain: str, columns: dict[str, str]) -> dict:
    start_close = base = prev_c = window[0][1]
    last_in: dict[str, float] = {}
    suspect = False
    for d, c in window:
        key = period_of(d, grain)
        last_in[key] = c
        columns[key] = max(columns.get(key, d), d)
        suspect = suspect or abs(c / prev_c - 1.0) >= SUSPECT_MOVE
        prev_c = c
    cells: dict[str, float] = {}
    for key in sorted(last_in):
        cells[key] = last_in[key] / base - 1.0
        base = last_in[key]
    return {
        "symbol": sym,
        "start": window[0][0],
        "start_close": start_close,
        "end_close": window[-1][1],
        "cells": cells,
        "total": window[-1][1] / start_close - 1.0,
        "suspect": suspect,
    }


def range_matrix(
    series_by_sym: dict[str, Series], start_by_sym: dict[str, str], end: str, grain: str
) -> dict:
    """Return per period for each stock, from its own start date (its tracking day) to ``end``.

    A period's return is its last close over the previous period's last close; the first
    period is measured from the close on the start date. ``total`` is end close over start.
    """
    columns: dict[str, str] = {}  # period key -> last trading date seen in it
    rows = []
    for sym, series in series_by_sym.items():
        start = start_by_sym.get(sym)
        if not start:
            continue
        lo = bisect_left(series, (start, float("-inf")))
        hi = bisect_right(series, (end, float("inf")))
        window = series[lo:hi]
        if not window:
            rows.append(
                {
                    "symbol": sym,
                    "start": start,
                    "start_close": None,
                    "end_close": None,
                    "cells": {},
                    "total": None,
                    "suspect": False,
                }
            )
            continue
        rows.append(_row(sym, window, grain, columns))
    cols = [{"key": k, "last_date": columns[k]} for k in sorted(columns)]
    return {"grain": grain, "columns": cols, "rows": rows}
