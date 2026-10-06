"""Market context: regime states, expiry phase counting, event badges."""
from app.services import screener_market as M


def _trend(start, step, n=220):
    return [start + step * i for i in range(n)]


def test_regime_on_off_caution():
    up = _trend(100, 0.5)
    assert M.regime(up, 0.7, 13.0)["state"] == "on"
    assert M.regime(up, 0.7, 13.0)["size_multiplier"] == 1.0
    assert M.regime(up, 0.45, 13.0)["state"] == "caution"          # narrow breadth
    assert M.regime(up, 0.7, 19.5)["state"] == "off"               # volatile rebound risk
    down = _trend(200, -0.5)
    r = M.regime(down, 0.8, 12.0)
    assert r["state"] == "off" and "200-day" in r["reasons"][0]
    assert M.regime(up[:100], 0.7, 12.0)["state"] == "caution"     # not enough history


def test_expiry_phase_counts_sessions_and_flags_window():
    days = ["2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23", "2026-10-26", "2026-10-27"]
    exp = ["2026-09-29", "2026-10-27", "2026-11-24"]
    p = M.expiry_phase(days, exp, "2026-10-21")
    assert p["next_expiry"] == "2026-10-27" and p["sessions_to_expiry"] == 4 and p["in_entry_window"]
    assert M.expiry_phase(days, exp, "2026-10-27")["phase"] == "expiry day"
    # calendar not known that far: count weekdays
    far = M.expiry_phase(days[:1], exp, "2026-10-20")
    assert far["sessions_to_expiry"] == 5 and far["phase"] == "early cycle"


def test_event_badges_window():
    b = M.event_badges("2026-10-06", "2026-10-26",
                       results=["2026-07-20", "2026-10-15"],
                       actions=[("2026-10-09", "DIVIDEND", 5.0), ("2026-11-02", "SPLIT", None),
                                ("2026-10-12", "OTHER", None)])
    assert [x["kind"] for x in b] == ["RESULTS", "DIVIDEND"]
    assert b[1]["amount"] == 5.0
