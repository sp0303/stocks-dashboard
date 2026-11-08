"""Golden: a hand-computed two-stock book through the full analytics report.

Book (all NSE, no charges):
  AAA buy 10 @ 100 (Mon 6 Jan), sell 10 @ 130 (Fri 10 Jan)  -> +300, 4 days, +30 %
  BBB buy 20 @ 50  (Mon 6 Jan), sell 10 @ 45 (Wed 15 Jan)  -> -50,  9 days, -10 %
  BBB remaining 10 @ 50, priced at 60 today                 -> open cost 500, value 600
  CCC buy 5 @ 10 and sell 5 @ 12 on Tue 7 Jan (intraday)    -> +10 in the intraday pool only
"""

from datetime import date, timedelta

from pi_core.analytics.client_report import DailyRow, ReportInputs, build_client_report
from pi_core.analytics.exposure import SecurityClass
from pi_core.models import Side, Trade

MON = date(2025, 1, 6)
TODAY = date(2025, 1, 17)
CAL = [MON + timedelta(i) for i in range(12) if (MON + timedelta(i)).weekday() < 5]


def _report():
    t = lambda i, d, s, side, q, p: Trade(str(i), d, s, "NSE", side, q, p)
    trades = [
        t(1, MON, "AAA", Side.BUY, 10, 100), t(2, MON + timedelta(4), "AAA", Side.SELL, 10, 130),
        t(3, MON, "BBB", Side.BUY, 20, 50), t(4, MON + timedelta(9), "BBB", Side.SELL, 10, 45),
        t(5, MON + timedelta(1), "CCC", Side.BUY, 5, 10), t(6, MON + timedelta(1), "CCC", Side.SELL, 5, 12),
    ]
    return build_client_report(ReportInputs(
        trades=trades, actions=[], calendar=CAL, price_lookup=lambda s, e, d: 60.0 if s == "BBB" else None,
        today=TODAY, classes={("AAA", "NSE"): SecurityClass("IT", "Large", "Equity"),
                              ("BBB", "NSE"): SecurityClass("Bank", "Mid", "Equity")},
        notes={"1": "results"}, manual_trades=[],
        daily=[DailyRow(d, 0.0, 0.0, 100.0, 0.0) for d in CAL], benchmarks=[],
    ))


def test_golden_trade_analytics():
    a = _report()["trades"]["delivery"]
    assert (a["closed_trades"], a["winning_trades"], a["losing_trades"]) == (2, 1, 1)
    assert a["win_rate"] == 0.5 and a["profit_factor"] == 6.0
    assert (a["avg_win"], a["avg_loss"], a["expectancy"], a["total_pnl"]) == (300, 50, 125, 250)
    assert a["avg_holding_days"] == 6.5
    assert [(p["cum_pnl"], p["drawdown"]) for p in a["equity_curve"]] == [(300, 0), (250, -50)]
    assert [b["bucket"] for b in a["distribution"]] == ["-10% to -5%", "20% to 50%"]
    assert [b["bucket"] for b in a["by_weekday"]] == ["Wed", "Fri"]


def test_golden_summary():
    s = _report()["summary"]
    assert s["intraday"] == {"trades": 1, "wins": 1, "win_rate": 1.0, "net_pnl": 10}
    cur = s["allocation"]["current"]["sector"]
    assert cur["total"] == 600 and cur["buckets"] == [{"key": "Bank", "value": 600, "weight": 1.0}]
    inv = s["allocation"]["invested"]["sector"]  # BBB open cost 500 + AAA peak 1000
    assert inv["total"] == 1500 and [(b["key"], b["value"]) for b in inv["buckets"]] == [("IT", 1000), ("Bank", 500)]
    assert s["concentration"]["largest_stock"]["symbol"] == "BBB"
    kinds = {h["kind"]: h for h in s["highlights"]}
    assert abs(kinds["best_open"]["value"] - 0.2) < 1e-12 and kinds["longest_held"]["value"] == 11
    assert kinds["best_closed"]["symbol"] == "AAA" and kinds["worst_closed"]["value"] == -50


def test_golden_playbook():
    rows = {r["symbol"]: r for r in _report()["playbook"]["delivery"]}
    assert rows["AAA"]["pnl"] == 300 and rows["AAA"]["pnl_pct"] == 0.3 and rows["AAA"]["reason"] == "results"
    assert rows["BBB"]["avg_buy_price"] == 50 and rows["BBB"]["avg_sell_price"] == 45 and rows["BBB"]["pnl_pct"] == -0.1
