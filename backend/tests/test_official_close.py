"""The daily store must carry NSE's official close, not the last traded minute."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "orb_official_close", Path(__file__).resolve().parents[1] / "scripts" / "orb_official_close.py")
oc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(oc)

HEADER = ("SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, LAST_PRICE, "
          "CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES, DELIV_QTY, DELIV_PER")


def _csv(*rows):
    return "\n".join([HEADER, *rows]) + "\n"


def test_uses_close_price_not_last_price():
    # Real 26-Oct-2026 row: last minute traded 1080.00, official close 1129.20.
    text = _csv(" CARBORUNIV, EQ, 26-Oct-2026, 1028.80, 1026.00, 1204.80, 1005.60, 1080.00, "
                "1129.20, 1104.55, 646123, 7136.75, 47507, 218694, 33.85")
    bar = oc.parse_bhavcopy(text, "2026-10-26")["CARBORUNIV"]
    assert bar == {"date": "2026-10-26", "o": 102600, "h": 120480, "l": 100560,
                   "c": 112920, "v": 646123, "src": "nse"}


def test_prefers_eq_series_and_skips_non_equity():
    text = _csv(
        "ABC, BE, 26-Oct-2026, 10, 10, 11, 9, 10, 10.50, 10, 100, 1, 1, 1, 1",
        "ABC, EQ, 26-Oct-2026, 10, 10, 11, 9, 10, 10.40, 10, 200, 1, 1, 1, 1",
        "GSEC, GS, 26-Oct-2026, 10, 10, 11, 9, 10, 10.00, 10, 5, 1, 1, 1, 1",
    )
    bars = oc.parse_bhavcopy(text, "2026-10-26")
    assert set(bars) == {"ABC"}
    assert bars["ABC"]["c"] == 1040 and bars["ABC"]["v"] == 200


def test_row_without_price_is_dropped_not_zeroed():
    text = _csv("XYZ, EQ, 26-Oct-2026, 10, -, -, -, -, -, -, 0, 0, 0, -, -")
    assert oc.parse_bhavcopy(text, "2026-10-26") == {}


def test_apply_writes_only_known_symbols_once_each(monkeypatch):
    saved = {}
    monkeypatch.setattr(oc.store, "save_daily", lambda s, rows: saved.setdefault(s, []).extend(rows))
    bar = lambda d, c: {"date": d, "o": c, "h": c, "l": c, "c": c, "v": 1, "src": "nse"}
    n = oc.apply({"2026-10-26": {"A": bar("2026-10-26", 100), "JUNK": bar("2026-10-26", 1)},
                  "2026-10-27": {"A": bar("2026-10-27", 110)}}, known={"A"})
    assert n == 1
    assert [r["c"] for r in saved["A"]] == [100, 110]
