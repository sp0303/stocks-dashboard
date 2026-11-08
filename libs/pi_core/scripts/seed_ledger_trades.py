"""Seed ledger.trades and let portfolio-worker compute derived tables."""

from datetime import date
import json
import os
import psycopg2
from pi_core.models import Side, Trade

DB_URL = os.environ["PG_DSN"]  # no hardcoded credentials (AGENTS §13)

def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    cur.execute("SELECT client_id FROM core.clients;")
    client_ids = [r[0] for r in cur.fetchall()]

    sample_trades = [
        Trade("T-101", date(2024, 1, 2), "RELIANCE", "NSE", Side.BUY, 50.0, 2400.0, charges=50.0),
        Trade("T-102", date(2024, 1, 15), "TCS", "NSE", Side.BUY, 30.0, 3500.0, charges=40.0),
        Trade("T-103", date(2024, 2, 10), "HDFCBANK", "NSE", Side.BUY, 100.0, 1450.0, charges=60.0),
        Trade("T-104", date(2024, 3, 5), "RELIANCE", "NSE", Side.SELL, 20.0, 2900.0, charges=30.0),
    ]

    for cid in client_ids:
        for t in sample_trades:
            # Seed securities
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

            # Insert into ledger.trades (fingerprint includes client_id + trade_id)
            fingerprint = f"{cid}_{t.trade_id}"
            cur.execute("""
                INSERT INTO ledger.trades (
                    client_id, fingerprint, symbol, exchange, trade_date,
                    trade_type, quantity, price, charges, charges_known, source
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, true, 'manual')
                ON CONFLICT (client_id, fingerprint) DO UPDATE SET quantity = EXCLUDED.quantity;
            """, (cid, fingerprint, t.symbol, t.exchange, t.trade_date, t.side.value.lower(), t.quantity, t.price, t.charges))

    conn.commit()
    conn.close()
    print(f"Seeded ledger.trades for {len(client_ids)} clients successfully!")

if __name__ == "__main__":
    main()
