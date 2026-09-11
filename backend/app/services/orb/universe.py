"""The tradeable set, derived rather than hardcoded.

Dropping the F&O universe (which this system no longer trades) also drops three
guarantees it was quietly providing, so they are re-imposed here explicitly:

  * **series must be EQ.** BE-series names are Trade-to-Trade — every trade takes
    delivery and *no intraday square-off is permitted*, so a signal on one is
    unexecutable. Note that services/angel.py deliberately folds -EQ and -BE into one
    symbol table for quote lookups; this module reads the series suffix instead, which
    is why it parses the scrip master itself rather than reusing that map.
  * **a 20% price band**, checked at runtime against the circuit limits the websocket
    reports in SNAP_QUOTE mode.
  * **liquidity**, re-imposed as a median-traded-value floor computed from our own
    daily candles.

The scrip master is Angel's public instrument dump, cached on disk for a day by
services/angel.py; this module reads the same cache file so the ~34 MB download is not
duplicated.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

log = logging.getLogger("orb.universe")

_SCRIP_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
_SCRIP_CACHE = Path(settings.data_dir) / "angel_scrip_master.json"
_MAX_AGE = 86400

# NSE index tokens (instrumenttype AMXIDX in the scrip master). Verified against a live
# fetch — note that 99926004 is Nifty 500, not an obvious guess.
INDEX_TOKENS = {
    "NIFTY 50": "99926000",
    "NIFTY BANK": "99926009",
    "NIFTY IT": "99926008",
    "NIFTY AUTO": "99926029",
    "NIFTY FMCG": "99926021",
    "NIFTY PHARMA": "99926023",
    "NIFTY METAL": "99926030",
    "NIFTY FIN SERVICE": "99926037",
    "NIFTY REALTY": "99926018",
    "NIFTY ENERGY": "99926020",
    "NIFTY PSU BANK": "99926025",
    "NIFTY MEDIA": "99926031",
    "NIFTY INFRA": "99926019",
    "INDIA VIX": "99926017",
}

MARKET_INDEX = "NIFTY 50"
VIX_INDEX = "INDIA VIX"

# Sector label (from app/data/nse_stocks.csv) -> the sector index used for alignment.
# Labels with no liquid sector index map to None: gate D5 is then skipped for that
# symbol and the signal trace records why, rather than silently passing.
SECTOR_TO_INDEX = {
    "Financial Services": "NIFTY FIN SERVICE",
    "Information Technology": "NIFTY IT",
    "Automobile": "NIFTY AUTO",
    "FMCG": "NIFTY FMCG",
    "Healthcare / Pharma": "NIFTY PHARMA",
    "Metals & Mining": "NIFTY METAL",
    "Energy / Oil & Gas": "NIFTY ENERGY",
    "Realty": "NIFTY REALTY",
    "Media": "NIFTY MEDIA",
    "Infrastructure": "NIFTY INFRA",
    "Power / Utilities": "NIFTY INFRA",
    "Capital Goods": None,
    "Consumer Services": None,
    "Consumer Durables": None,
    "Telecommunication": None,
    "Chemicals": None,
    "Cement & Building Materials": None,
}


@dataclass(frozen=True)
class Instrument:
    symbol: str
    token: str
    series: str          # "EQ" or "BE"
    tick: int            # paise: 1, 5 or 10 depending on the name
    exchange: str = "NSE"

    @property
    def tradeable_intraday(self) -> bool:
        return self.series == "EQ"


_rows: list[dict] | None = None


def _load_scrip_master(force: bool = False) -> list[dict]:
    global _rows
    if _rows is not None and not force:
        return _rows
    data = None
    try:
        if _SCRIP_CACHE.exists() and (time.time() - _SCRIP_CACHE.stat().st_mtime) < _MAX_AGE:
            data = json.loads(_SCRIP_CACHE.read_text())
    except Exception:
        data = None
    if data is None:
        import httpx

        r = httpx.get(_SCRIP_URL, timeout=120.0)
        r.raise_for_status()
        data = r.json()
        try:
            _SCRIP_CACHE.parent.mkdir(parents=True, exist_ok=True)
            _SCRIP_CACHE.write_text(r.text)
        except Exception as exc:
            log.warning("could not cache scrip master: %s", exc)
    _rows = data
    return _rows


def all_nse_cash(force: bool = False) -> list[Instrument]:
    """Every NSE cash instrument, series preserved. ~2,676 EQ and ~239 BE."""
    out: list[Instrument] = []
    for row in _load_scrip_master(force):
        if row.get("exch_seg") != "NSE":
            continue
        sym = row.get("symbol") or ""
        if "-" not in sym:
            continue
        base, series = sym.rsplit("-", 1)
        if series not in ("EQ", "BE"):
            continue
        try:
            tick = int(round(float(row.get("tick_size") or 5) / 100.0 * 100))
        except (TypeError, ValueError):
            tick = 5
        out.append(Instrument(symbol=base, token=str(row["token"]), series=series,
                              tick=max(1, tick)))
    return out


def equity_candidates(force: bool = False) -> list[Instrument]:
    """The starting pool: NSE EQ series only. BE is excluded here, once, so no
    downstream stage has to remember to."""
    return [i for i in all_nse_cash(force) if i.tradeable_intraday]


def index_instruments(force: bool = False) -> dict[str, str]:
    """{index name: token}, confirmed against the scrip master so a renamed or retired
    index surfaces as a missing key instead of a silently wrong series."""
    present = {str(r.get("token")) for r in _load_scrip_master(force)
               if r.get("instrumenttype") == "AMXIDX" and r.get("exch_seg") == "NSE"}
    found = {name: tok for name, tok in INDEX_TOKENS.items() if tok in present}
    missing = set(INDEX_TOKENS) - set(found)
    if missing:
        log.warning("index tokens not found in scrip master: %s", sorted(missing))
    return found


_sector_labels: dict[str, str] | None = None


def _load_sector_labels() -> dict[str, str]:
    """Read the seed classification CSV directly rather than going through
    services.securities.classify: that path depends on init_cache() having run at app
    startup and falls through to a network lookup on a miss. The engine needs a
    deterministic, offline answer on every bar."""
    global _sector_labels
    if _sector_labels is not None:
        return _sector_labels
    import csv

    out: dict[str, str] = {}
    path = Path(settings.data_dir) / "nse_stocks.csv"
    try:
        with path.open(newline="") as fh:
            for row in csv.DictReader(fh):
                sym = (row.get("symbol") or "").strip().upper()
                sec = (row.get("sector") or "").strip()
                if sym and sec:
                    out[sym] = sec
    except Exception as exc:
        log.warning("sector seed unavailable (%s) — gate D5 will be skipped", exc)
    _sector_labels = out
    return out


def sector_index_for(symbol: str) -> str | None:
    """The sector index a symbol should be aligned against, or None when we have no
    mapping — in which case gate D5 records 'no sector index' rather than passing."""
    label = _load_sector_labels().get(symbol.upper())
    return SECTOR_TO_INDEX.get(label) if label else None
