"""Pure normalisation of research.screener_snapshots payloads into a typed row list.

The payload was produced by the v1 screener, where momentum fields (d1/w1/m1,
from_52w_high) are in percent. Rule R12: the API returns ratios as decimals, so
they are divided by 100 here unless the payload declares ``"units": "decimal"``.
"""

from __future__ import annotations

import math
from typing import Any

_PCT_FIELDS = ("d1", "w1", "m1", "y1", "from_52w_high")
_EVENT_KINDS = {"RESULTS", "DIVIDEND", "BONUS", "SPLIT", "RIGHTS", "BUYBACK", "DEMERGER"}
_NUM_FIELDS = (
    "score",
    "rank",
    "value_score",
    "quality_score",
    "rsi",
    "rel_strength",
    "price",
)


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _rows_of(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("stocks", "rows", "items"):
            if isinstance(payload.get(key), list):
                return [r for r in payload[key] if isinstance(r, dict)]
    return []


def _hold_days(r: dict[str, Any]) -> float | None:
    plan = r.get("plan") if isinstance(r.get("plan"), dict) else {}
    for v in (
        plan.get("expected_hold_days"),
        r.get("expected_hold_days"),
        r.get("typical_hold_days"),
    ):
        n = _num(v)
        if n is not None:
            return n
    return None


def _setup(r: dict[str, Any]) -> str | None:
    v = r.get("setup")
    if isinstance(v, dict):  # tolerate {"label": ...}
        v = v.get("label") or v.get("name")
    return str(v) if v else None


def _events(r: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for e in r.get("events") or []:
        if not isinstance(e, dict) or str(e.get("kind", "")).upper() not in _EVENT_KINDS:
            continue
        if not e.get("date"):
            continue
        out.append({"kind": str(e["kind"]).upper(), "date": str(e["date"])[:10],
                    "amount": _num(e.get("amount"))})
    return out


def market_context(payload: Any) -> dict[str, Any] | None:
    """v1's regime / F&O expiry phase / events window, passed through (advisory context)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("market"), dict):
        return None
    m = payload["market"]
    reg = m.get("regime") if isinstance(m.get("regime"), dict) else None
    exp = m.get("expiry") if isinstance(m.get("expiry"), dict) else None
    return {
        "regime": {
            "state": reg.get("state"),
            "size_multiplier": _num(reg.get("size_multiplier")),
            "reasons": [str(x) for x in reg.get("reasons") or []],
            "breadth": _num(reg.get("breadth")),  # already a 0..1 fraction in v1
            "vix": _num(reg.get("vix")),
        } if reg else None,
        "expiry": {
            "next_expiry": exp.get("next_expiry"),
            "sessions_to_expiry": _num(exp.get("sessions_to_expiry")),
            "phase": exp.get("phase"),
            "in_entry_window": exp.get("in_entry_window"),
            "calendar": exp.get("calendar"),
        } if exp else None,
        "regime_basis": m.get("regime_basis"),
        "events_window": m.get("events_window") if isinstance(m.get("events_window"), dict) else None,
    }


def snapshot_meta(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"data_as_of": None, "generated_at": None, "source": None}
    return {
        "data_as_of": payload.get("data_as_of"),
        "generated_at": payload.get("generated_at"),
        "source": payload.get("source"),
    }


def normalise_row(r: dict[str, Any], pct_divisor: float) -> dict[str, Any] | None:
    symbol = r.get("ticker") or r.get("symbol")
    if not symbol:
        return None
    out: dict[str, Any] = {
        "symbol": str(symbol).upper(),
        "name": r.get("name"),
        "sector": r.get("sector") or None,
        "setup": _setup(r),
        "typical_hold_days": _hold_days(r),
        "events": _events(r),
    }
    for f in _NUM_FIELDS:
        out[f] = _num(r.get(f))
    for f in _PCT_FIELDS:
        n = _num(r.get(f))
        out[f] = n / pct_divisor if n is not None else None
    return out


def normalise_snapshot(payload: Any) -> list[dict[str, Any]]:
    declared = payload.get("units") if isinstance(payload, dict) else None
    divisor = 1.0 if declared == "decimal" else 100.0
    rows = [normalise_row(r, divisor) for r in _rows_of(payload)]
    return [r for r in rows if r is not None]
