"""Forward-test journal — "if I had bought the screen, where would I be now?"

For each saved screen (a Phase-5 snapshot), buy one share of every stock in a group
(top 20, top 50, top-50 tradable setups, whole universe) and mark it at a fixed number of
sessions later. Two entries are reported, because the gap between them is real money:

  * paper — the signal close itself (what the screen priced in; not actually achievable)
  * real  — the NEXT session's open (the earliest a reader of the screen could act)

The universe average is the benchmark: the screener ranks stocks, it does not time the
market, so "beat the average stock" is the question it must answer. Pure functions only;
rows are the daily store shape {"date","o","h","l","c" (paise),"v"}.
"""
from __future__ import annotations

from collections import Counter

from app.services.screener_setups import TRADABLE

HORIZONS = (3, 5, 7, 10)
GROUPS = ("top20", "top50", "top50_setup", "universe")


def infer_data_date(stocks: list[dict], rows_by_ticker: dict[str, list[dict]],
                    sample: int = 40) -> str | None:
    """The close a snapshot was actually computed from: the date whose close equals the
    stored entry price for the most stocks. Needed because old snapshots were labelled by
    the day they were *computed*, not the day their data is from."""
    votes: Counter = Counter()
    for st in [s for s in stocks if s.get("entry")][:sample]:
        for r in rows_by_ticker.get(st["ticker"], [])[-80:]:
            if abs(r["c"] / 100 - st["entry"]) < 0.011:
                votes[r["date"]] += 1
    return votes.most_common(1)[0][0] if votes else None


def is_stale(data_date: str, created_date: str, trading_dates: list[str]) -> bool:
    """A screen first shown after a later session had already closed could not have been
    acted on at the next open — e.g. a 15 Sep screen still built from the 10 Sep close.
    Such windows overstate what a reader could achieve, so they are left out."""
    return any(data_date < d < created_date for d in trading_dates)


def ranked(stocks: list[dict]) -> list[dict]:
    """Rank by composite score, best first (same order as the live screen)."""
    out = sorted(stocks, key=lambda s: s.get("score") if s.get("score") is not None else -1e9,
                 reverse=True)
    return [{**s, "rank": i} for i, s in enumerate(out, 1)]


def trade(st: dict, after: list[dict], horizon: int) -> dict | None:
    """One share held `horizon` sessions. `after` = daily rows strictly after the signal
    date. None until the horizon has matured or when a price is missing."""
    if len(after) < horizon or not st.get("entry"):
        return None
    entry_open = after[0]["o"] / 100
    exit_close = after[horizon - 1]["c"] / 100
    if entry_open <= 0:
        return None
    return {
        "ticker": st["ticker"], "rank": st["rank"], "setup": st.get("setup"),
        "entry_close": st["entry"], "entry_open": entry_open, "exit_close": exit_close,
        "exit_date": after[horizon - 1]["date"],
        "ret_paper": exit_close / st["entry"] - 1,
        "ret_real": exit_close / entry_open - 1,
    }


def summarize(trades: list[dict]) -> dict | None:
    """Equal-weight (1 share each is reported in rupees too). Returns are decimals (R12)."""
    n = len(trades)
    if not n:
        return None
    return {
        "n": n,
        "avg_real": sum(t["ret_real"] for t in trades) / n,
        "avg_paper": sum(t["ret_paper"] for t in trades) / n,
        "win_rate": sum(t["ret_real"] > 0 for t in trades) / n,
        "rupees_1sh": sum(t["exit_close"] - t["entry_open"] for t in trades),
        "invested_1sh": sum(t["entry_open"] for t in trades),
    }


def in_group(t: dict, group: str) -> bool:
    if group == "top20":
        return t["rank"] <= 20
    if group == "top50":
        return t["rank"] <= 50
    if group == "top50_setup":
        return t["rank"] <= 50 and t.get("setup") in TRADABLE
    return True


def journal(stocks: list[dict], after_by_ticker: dict[str, list[dict]], signal_date: str,
            horizons=HORIZONS) -> list[dict]:
    """One row per matured horizon: each group's result and its excess over the universe."""
    rk = ranked(stocks)
    out = []
    for h in horizons:
        trades = [x for x in (trade(s, after_by_ticker.get(s["ticker"], []), h) for s in rk) if x]
        if not trades:
            continue
        groups = {g: summarize([t for t in trades if in_group(t, g)]) for g in GROUPS}
        uni = groups["universe"]["avg_real"]
        row = {"_id": f"{signal_date}:{h}", "signal_date": signal_date, "horizon": h,
               "exit_date": max(t["exit_date"] for t in trades), "groups": groups,
               "excess": {g: (groups[g]["avg_real"] - uni) if groups[g] else None
                          for g in GROUPS if g != "universe"}}
        out.append(row)
    return out


def rollup(rows: list[dict], horizon: int) -> dict:
    """Across all signal dates at one horizon: mean excess and how often each group beat
    the universe. Overlapping windows are correlated — treat the hit-rate as indicative."""
    rs = [r for r in rows if r["horizon"] == horizon]
    res = {"horizon": horizon, "windows": len(rs)}
    for g in ("top20", "top50", "top50_setup"):
        ex = [r["excess"][g] for r in rs if r["excess"].get(g) is not None]
        res[g] = {
            "mean_excess": sum(ex) / len(ex) if ex else None,
            "beat_rate": sum(e > 0 for e in ex) / len(ex) if ex else None,
            "mean_abs": (sum(r["groups"][g]["avg_real"] for r in rs if r["groups"][g]) / len(ex))
            if ex else None,
        }
    uni = [r["groups"]["universe"]["avg_real"] for r in rs]
    res["universe_mean"] = sum(uni) / len(uni) if uni else None
    return res
