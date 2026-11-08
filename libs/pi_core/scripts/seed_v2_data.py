"""Seed initial demo portfolios into v2 database to test end-to-end stack."""

from datetime import date
import json
import os
import psycopg2
from pi_core.engine.fifo import FIFOEngine
from pi_core.metrics.capital import calculate_capital_metrics
from pi_core.metrics.returns import calculate_returns
from pi_core.metrics.risk import calculate_risk_metrics
from pi_core.metrics.drawdown import calculate_drawdown_series
from pi_core.models import Side, Trade
from pi_core.series.calendar import generate_trading_calendar
from pi_core.series.twr import calculate_twr_series

DB_URL = os.environ["PG_DSN"]  # no hardcoded credentials (AGENTS §13)

def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    print("Checking existing managers...")
    cur.execute("SELECT manager_id FROM core.managers LIMIT 1;")
    row = cur.fetchone()
    if not row:
        cur.execute("""
            INSERT INTO core.managers (name, firm, email)
            VALUES ('Demo Manager', 'Demo Desk', 'manager@example.com')
            RETURNING manager_id;
        """)
        manager_id = cur.fetchone()[0]
        print(f"Created manager: {manager_id}")
    else:
        manager_id = row[0]

    # Create demo clients
    clients_to_create = [
        ("Demo Client", "DEMO0001", "ZERODHA"),
        ("Alpha Growth Fund", "AGF001", "UPSTOX"),
    ]

    for c_name, c_code, c_broker in clients_to_create:
        cur.execute("SELECT client_id FROM core.clients WHERE client_code = %s;", (c_code,))
        c_row = cur.fetchone()
        if not c_row:
            cur.execute("""
                INSERT INTO core.clients (manager_id, name, client_code, broker)
                VALUES (%s, %s, %s, %s)
                RETURNING client_id;
            """, (manager_id, c_name, c_code, c_broker))
            client_id = cur.fetchone()[0]
            print(f"Created client {c_name}: {client_id}")
        else:
            client_id = c_row[0]

        # Seed sample trades
        sample_trades = [
            Trade("T-101", date(2024, 1, 2), "RELIANCE", "NSE", Side.BUY, 50.0, 2400.0, charges=50.0),
            Trade("T-102", date(2024, 1, 15), "TCS", "NSE", Side.BUY, 30.0, 3500.0, charges=40.0),
            Trade("T-103", date(2024, 2, 10), "HDFCBANK", "NSE", Side.BUY, 100.0, 1450.0, charges=60.0),
            Trade("T-104", date(2024, 3, 5), "RELIANCE", "NSE", Side.SELL, 20.0, 2900.0, charges=30.0),
        ]

        # Seed securities
        for t in sample_trades:
            cur.execute("""
                INSERT INTO market.securities (symbol, exchange, name)
                VALUES (%s, %s, %s)
                ON CONFLICT (symbol, exchange) DO UPDATE SET is_active = true
                RETURNING security_id;
            """, (t.symbol, t.exchange, t.symbol))
            sec_id = cur.fetchone()[0]

            # Insert eod close price
            cur.execute("""
                INSERT INTO market.eod_prices (security_id, price_date, close, source)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (security_id, price_date) DO UPDATE SET close = EXCLUDED.close;
            """, (sec_id, date(2024, 3, 20), t.price * 1.05, "NSE"))

        # Run FIFO engine
        calendar = generate_trading_calendar(date(2024, 1, 1), date(2024, 3, 20))
        def price_lookup(sym, exch, d):
            return 2950.0 if sym == "RELIANCE" else (3900.0 if sym == "TCS" else 1550.0)

        engine = FIFOEngine(sample_trades, price_lookup=price_lookup)
        result = engine.run(calendar)

        nav_series, _ = calculate_twr_series(result.snapshots, sample_trades)
        cap_metrics = calculate_capital_metrics(result.snapshots)
        ret_summary = calculate_returns(nav_series)
        risk_summary = calculate_risk_metrics(nav_series)
        dd_summary = calculate_drawdown_series(nav_series)

        # Write client_overview
        overview_payload = {
            "market_value": cap_metrics.market_value if cap_metrics else 0.0,
            "capital_deployed": cap_metrics.capital_deployed if cap_metrics else 0.0,
            "current_invested": cap_metrics.current_invested if cap_metrics else 0.0,
            "realized_pnl": cap_metrics.realized_pnl if cap_metrics else 0.0,
            "unrealized_pnl": cap_metrics.unrealized_pnl if cap_metrics else 0.0,
            "total_pnl": cap_metrics.total_pnl if cap_metrics else 0.0,
            "return_on_capital": cap_metrics.return_on_capital if cap_metrics else 0.0,
            "cagr": ret_summary.cagr if ret_summary else None,
        }

        cur.execute("""
            INSERT INTO portfolio.client_overview (client_id, as_of, payload, engine_version)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (client_id) DO UPDATE SET payload = EXCLUDED.payload, as_of = EXCLUDED.as_of;
        """, (client_id, date(2024, 3, 20), json.dumps(overview_payload), "v2.0"))

        # Write client_metrics
        metrics_payload = {
            "total_return": ret_summary.total_return if ret_summary else 0.0,
            "cagr": ret_summary.cagr if ret_summary else None,
            "annualized_volatility": risk_summary.annualized_volatility if risk_summary else None,
            "sharpe_ratio": risk_summary.sharpe_ratio if risk_summary else None,
            "max_drawdown": dd_summary.max_drawdown if dd_summary else None,
            "current_drawdown": dd_summary.current_drawdown if dd_summary else None,
            "xirr": 0.284,
        }

        cur.execute("""
            INSERT INTO portfolio.client_metrics (client_id, as_of, obs, payload, engine_version)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (client_id) DO UPDATE SET payload = EXCLUDED.payload;
        """, (client_id, date(2024, 3, 20), len(nav_series), json.dumps(metrics_payload), "v2.0"))

        # Write client_daily series
        for pt in nav_series:
            cur.execute("""
                INSERT INTO portfolio.client_daily (
                    client_id, as_of, market_value, open_cost, net_invested,
                    realized_pnl, nav, day_return, engine_version
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (client_id, as_of) DO UPDATE SET
                    nav = EXCLUDED.nav, market_value = EXCLUDED.market_value;
            """, (client_id, pt.point_date, pt.market_value, pt.capital_base, pt.market_value, 0.0, pt.nav, pt.daily_return, "v2.0"))

        # Write positions_latest
        for (sym, exch), lots in result.open_lots.items():
            cur.execute("SELECT security_id FROM market.securities WHERE symbol = %s AND exchange = %s;", (sym, exch))
            sec_id = cur.fetchone()[0]
            tot_qty = sum(l.quantity for l in lots)
            tot_cost = sum(l.total_cost for l in lots)
            avg_c = tot_cost / tot_qty if tot_qty > 0 else 0.0

            cur.execute("""
                INSERT INTO portfolio.positions_latest (client_id, security_id, quantity, avg_cost, invested, entry_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (client_id, security_id) DO UPDATE SET
                    quantity = EXCLUDED.quantity, avg_cost = EXCLUDED.avg_cost, invested = EXCLUDED.invested;
            """, (client_id, sec_id, tot_qty, avg_c, tot_cost, date(2024, 1, 2)))

    conn.commit()
    conn.close()
    print("Seeding completed successfully!")

if __name__ == "__main__":
    main()
