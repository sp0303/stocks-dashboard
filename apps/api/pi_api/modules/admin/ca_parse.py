"""Pure NSE corporate-action parsing (ported from v1 backend/app/services/corporate_actions.py).

No I/O. Used by ``pi_workers.ca_refresh_worker``; kept here so the parsing is unit-testable
and the worker stays within the module size limit (AGENTS §3.14).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

_RS = r"(?:rs|re|inr)?\.?\s*/?-?\s*([\d]+(?:\.\d+)?)"


def iso_date(d: str | None) -> date | None:
    if not d or d.strip() in ("-", "0", ""):
        return None
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(d.strip(), fmt).date()  # noqa: DTZ007 — a calendar date, no time
        except ValueError:
            continue
    return None


def parse_action(subject: str) -> dict[str, Any]:
    """Classify an NSE subject. qty_multiplier only for SPLIT/BONUS with a parsed ratio (R8)."""
    low = (subject or "").strip().lower()
    out: dict[str, Any] = {
        "type": "OTHER",
        "qty_multiplier": None,
        "amount_per_share": None,
    }
    if (
        "split" in low
        or "sub-division" in low
        or "sub division" in low
        or ("face value" in low and "from" in low)
    ):
        m = re.search(r"from\s+" + _RS + r".*?to\s+" + _RS, low)
        out["type"] = "SPLIT"
        if m and 0 < float(m.group(2)) < float(m.group(1)):
            out["qty_multiplier"] = float(m.group(1)) / float(m.group(2))
        return out
    if "bonus" in low:
        m = re.search(r"bonus\s+(\d+)\s*:\s*(\d+)", low)
        out["type"] = "BONUS"
        if m and int(m.group(2)) > 0:
            out["qty_multiplier"] = (int(m.group(1)) + int(m.group(2))) / int(
                m.group(2)
            )
        return out
    for words, kind in (
        (("demerger", "de-merger"), "DEMERGER"),
        (("buy back", "buyback", "buy-back"), "BUYBACK"),
        (("amalgamation", "merger", "scheme of arrangement"), "MERGER"),
        (("delisting", "delist"), "DELISTING"),
        (("rights",), "RIGHTS"),
    ):
        if any(w in low for w in words):
            out["type"] = kind
            return out
    if "dividend" in low:
        m = re.search(r"dividend[^0-9]*" + _RS, low)
        out.update(type="DIVIDEND", amount_per_share=float(m.group(1)) if m else None)
    return out


def normalize(rec: dict[str, Any]) -> dict[str, Any] | None:
    """One raw NSE record -> a ledger.corporate_actions row, or None (undated / not holding-affecting)."""
    ex = iso_date(rec.get("exDate"))
    subject = (rec.get("subject") or "").strip()
    parsed = parse_action(subject)
    symbol = (rec.get("symbol") or "").strip().upper()
    if parsed["type"] == "OTHER" or ex is None or not symbol:
        return None
    isin = (rec.get("isin") or "").strip() or None
    mult = parsed["qty_multiplier"]
    return {
        "key": f"{isin or symbol}|{ex.isoformat()}|{parsed['type']}|{subject[:60]}",
        "isin": isin,
        "symbol": symbol,
        "ex_date": ex,
        "type": parsed["type"],
        "qty_multiplier": round(mult, 8) if mult is not None else None,
        "amount_per_share": parsed["amount_per_share"],
        "subject": subject or None,
        "source": "NSE",
    }


def parse_equity_list(text: str) -> list[str]:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return []
    header = [h.strip().upper() for h in lines[0].split(",")]
    idx = header.index("SYMBOL") if "SYMBOL" in header else 0
    return sorted(
        {
            p[idx].strip().upper()
            for p in (ln.split(",") for ln in lines[1:])
            if len(p) > idx and p[idx].strip()
        }
    )
