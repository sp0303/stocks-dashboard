"""Phase 5 — the forward-performance loop (permanent).

Everything before this is *backtested* expectancy. Phase 5 is the live feedback: snapshot
every scan, then — once enough sessions have passed — record what actually happened, and
report the **realized** rank-IC and per-setup expectancy. A decaying factor or a setup that
has stopped working shows up here in real time, before it costs money. Given Phases 1–2
proved the edge is regime-sensitive and can decay, this loop is the safety net, not a luxury.

Design: the pure functions (forward returns, MFE/MAE, first-touch, IC, the realized report)
have no I/O and are fully unit-tested; persistence is thin Mongo wrappers, and outcome
recording takes a `forward_lookup` callback so it can be driven live, from a backfill, or
from a fake in tests. Prices in the store are integer paise; snapshots store rupees.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

SNAP_COLL = "screener_snapshots"
HORIZONS = (3, 5, 10, 20)


# ── pure outcome maths ────────────────────────────────────────────
def forward_returns(future_closes: list[float], entry: float,
                    horizons=HORIZONS) -> dict[int, float]:
    """% return at each horizon, using the close `h` sessions after entry (1-indexed)."""
    out = {}
    for h in horizons:
        if 0 < h <= len(future_closes) and entry:
            out[h] = (future_closes[h - 1] - entry) / entry * 100
    return out


def mfe_mae(future_rows: list[dict], entry: float, horizon: int) -> tuple[float | None, float | None]:
    """Max favourable / adverse excursion over the next `horizon` sessions, in %."""
    window = future_rows[:horizon]
    if not window or not entry:
        return None, None
    hi = max(r["h"] / 100 for r in window)
    lo = min(r["l"] / 100 for r in window)
    return (hi - entry) / entry * 100, (lo - entry) / entry * 100


def first_touch(future_rows: list[dict], entry: float, stop: float, target: float,
                horizon: int) -> tuple[str, int]:
    """Which of stop/target the price touches first over `horizon` sessions (stop wins a
    same-bar tie — the conservative read). ('stop'|'target'|'time', hold_days)."""
    for d, r in enumerate(future_rows[:horizon], start=1):
        lo, hi = r["l"] / 100, r["h"] / 100
        if lo <= stop:
            return "stop", d
        if hi >= target:
            return "target", d
    return "time", min(horizon, len(future_rows))


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 8:
        return None

    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    return num / (dx * dy) if dx and dy else None


# ── snapshot construction ─────────────────────────────────────────
def snapshot_from_compute(compute_result: dict, as_of: str) -> dict:
    """Freeze the fields Phase 5 needs to judge itself later: per stock the composite score,
    setup label, value/quality context, and the plan levels (entry/stop/targets)."""
    rows = []
    for s in compute_result.get("stocks", []):
        plan = s.get("plan") or {}
        rows.append({
            "ticker": s["ticker"], "setup": s.get("setup"), "score": s.get("score"),
            "value_score": s.get("value_score"), "quality_score": s.get("quality_score"),
            "entry": plan.get("entry") or s.get("price"),
            "stop": plan.get("stop"), "t2": plan.get("t2"),
            "risk_per_share": plan.get("risk_per_share"),
        })
    return {"_id": as_of, "as_of": as_of,
            "created_at": datetime.now(timezone.utc).isoformat(), "stocks": rows}


def record_outcomes(snapshot: dict, forward_lookup, *, horizons=HORIZONS,
                    cost_pct: float = 0.30, min_bars: int | None = None) -> dict:
    """Fill each stock's realized outcome using `forward_lookup(ticker, as_of) -> future rows`
    (the daily docs strictly AFTER as_of). Skips a snapshot until at least `min_bars`
    (default max horizon) of forward data exist for a representative name, so partial windows
    don't create half-measured outcomes. Returns the snapshot with an `outcomes` block added
    per stock; idempotent."""
    need = min_bars if min_bars is not None else max(horizons)
    matured = 0
    for st in snapshot["stocks"]:
        entry = st.get("entry")
        if not entry:
            continue
        fut = forward_lookup(st["ticker"], snapshot["as_of"]) or []
        if len(fut) < need:
            continue
        closes = [r["c"] / 100 for r in fut]
        fr = forward_returns(closes, entry, horizons)
        fr_net = {h: v - cost_pct for h, v in fr.items()}
        mfe, mae = mfe_mae(fut, entry, max(horizons))
        outcome = {"ret": fr, "ret_net": fr_net, "mfe": mfe, "mae": mae}
        if st.get("stop") and st.get("t2") and st.get("setup") not in (None, "No setup"):
            res, hold = first_touch(fut, entry, st["stop"], st["t2"], max(horizons))
            rps = st.get("risk_per_share") or (entry - st["stop"])
            exit_px = {"stop": st["stop"], "target": st["t2"],
                       "time": closes[min(max(horizons), len(closes)) - 1]}[res]
            cost_r = (cost_pct / 100 * entry) / rps if rps else 0.0
            outcome.update({"first_touch": res, "hold": hold,
                            "r_net": ((exit_px - entry) / rps - cost_r) if rps else None})
        st["outcomes"] = outcome
        matured += 1
    snapshot["matured"] = matured
    return snapshot


# ── realized report ───────────────────────────────────────────────
def realized_report(snapshots: list[dict], horizon: int = 10) -> dict:
    """Pool matured snapshots into realized rank-IC (composite score vs net forward return at
    `horizon`) and per-setup realized expectancy in R. This is the live mirror of the
    backtest's gates — watch it drift."""
    ic_pairs_score, ic_pairs_ret = [], []
    per_setup = defaultdict(list)
    dated_ic = []
    for snap in snapshots:
        s_x, s_y = [], []
        for st in snap.get("stocks", []):
            oc = st.get("outcomes")
            if not oc or st.get("score") is None:
                continue
            rn = oc.get("ret_net", {}).get(horizon)
            if rn is None:
                continue
            s_x.append(st["score"])
            s_y.append(rn)
            if st.get("setup") and st["setup"] != "No setup" and oc.get("r_net") is not None:
                per_setup[st["setup"]].append(oc["r_net"])
        if len(s_x) >= 8:
            ic = _spearman(s_x, s_y)
            if ic is not None:
                dated_ic.append((snap["as_of"], ic))
            ic_pairs_score += s_x
            ic_pairs_ret += s_y

    pooled_ic = _spearman(ic_pairs_score, ic_pairs_ret) if len(ic_pairs_score) >= 8 else None
    setups = {k: {"n": len(v), "exp_r": round(sum(v) / len(v), 3)}
              for k, v in per_setup.items() if v}
    return {"horizon": horizon, "snapshots_scored": len(dated_ic),
            "pooled_realized_ic": round(pooled_ic, 4) if pooled_ic is not None else None,
            "rolling_ic": [(d, round(i, 4)) for d, i in dated_ic[-12:]],
            "setup_expectancy_r": setups, "pairs": len(ic_pairs_score)}


# ── thin Mongo persistence ────────────────────────────────────────
def save_snapshot(db, snapshot: dict) -> None:
    """Upsert by _id=as_of, so re-running a scan on the same day overwrites, never duplicates."""
    db[SNAP_COLL].replace_one({"_id": snapshot["_id"]}, snapshot, upsert=True)


def load_snapshots(db, limit: int = 400) -> list[dict]:
    return list(db[SNAP_COLL].find().sort("_id", -1).limit(limit))
