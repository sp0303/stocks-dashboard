"""Forward-test journal: data-date inference, next-open entry, horizons, groups, excess."""
from app.services import screener_journal as J


def _row(date, o, c):
    return {"date": date, "o": int(o * 100), "h": int(max(o, c) * 100),
            "l": int(min(o, c) * 100), "c": int(c * 100), "v": 1}


def test_infer_data_date_uses_the_close_that_matches_entry():
    rows = {"A": [_row("2026-09-23", 100, 101), _row("2026-09-24", 101, 105)],
            "B": [_row("2026-09-23", 50, 52), _row("2026-09-24", 52, 49)]}
    stocks = [{"ticker": "A", "entry": 105.0}, {"ticker": "B", "entry": 49.0}]
    # snapshot *labelled* 25 Sep but built from the 24 Sep close
    assert J.infer_data_date(stocks, rows) == "2026-09-24"


def test_stale_screen_is_detected():
    days = ["2026-09-10", "2026-09-11", "2026-09-14", "2026-09-15", "2026-10-01", "2026-10-05"]
    assert J.is_stale("2026-09-10", "2026-09-15", days)       # 11th and 14th closed in between
    assert not J.is_stale("2026-10-01", "2026-10-05", days)   # only a holiday + weekend between
    assert not J.is_stale("2026-09-24", "2026-09-25", days)   # morning after: actionable


def test_trade_enters_next_open_and_waits_for_maturity():
    st = {"ticker": "A", "rank": 1, "setup": "Near breakout", "entry": 100.0}
    after = [_row("d1", 102, 103), _row("d2", 103, 104), _row("d3", 104, 110)]
    assert J.trade(st, after, 5) is None                      # not matured
    t = J.trade(st, after, 3)
    assert t["entry_open"] == 102 and t["exit_close"] == 110
    assert abs(t["ret_real"] - (110 / 102 - 1)) < 1e-12        # realistic: next open
    assert abs(t["ret_paper"] - 0.10) < 1e-12                  # paper: signal close


def test_groups_and_excess_vs_universe():
    # 60 stocks; the 20 best-scored rise 5%, everything else falls 1%
    stocks, after = [], {}
    for i in range(60):
        tk = f"S{i}"
        stocks.append({"ticker": tk, "score": 100 - i, "entry": 100.0,
                       "setup": "Pullback setup" if i < 10 else "No setup"})
        after[tk] = [_row("d1", 100, 105 if i < 20 else 99)] * 3
    (row,) = J.journal(stocks, after, "2026-09-24", horizons=(3,))
    g = row["groups"]
    assert g["top20"]["n"] == 20 and abs(g["top20"]["avg_real"] - 0.05) < 1e-12
    assert g["top50_setup"]["n"] == 10                       # only tradable labels
    uni = (20 * 0.05 + 40 * -0.01) / 60
    assert abs(g["universe"]["avg_real"] - uni) < 1e-12
    assert abs(row["excess"]["top20"] - (0.05 - uni)) < 1e-12
    assert row["_id"] == "2026-09-24:3"


def test_rollup_beat_rate():
    rows = [{"horizon": 3, "excess": {"top20": e, "top50": e, "top50_setup": None},
             "groups": {"top20": {"avg_real": e}, "top50": {"avg_real": e}, "top50_setup": None,
                        "universe": {"avg_real": 0.0}}} for e in (0.02, -0.01, 0.03)]
    r = J.rollup(rows, 3)
    assert r["windows"] == 3 and abs(r["top20"]["beat_rate"] - 2 / 3) < 1e-12
    assert r["top50_setup"]["mean_excess"] is None
