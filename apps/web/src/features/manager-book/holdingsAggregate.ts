import type { HoldingClientItem, ManagerHoldingsItem } from '@/lib/api';

export interface BookHoldingRow {
  symbol: string;
  exchange: string;
  price: number | null;
  priceAsOf: string | null;
  pricedOn: string | null;
  quantity: number;
  invested: number;
  marketValue: number | null;
  unrealized: number | null;
  returnPct: number | null;
  clients: (HoldingClientItem & { marketValue: number | null })[];
}

export interface BookHoldingTotals {
  invested: number;
  marketValue: number;
  unrealized: number;
  returnPct: number | null;
  unpriced: number;
}

/**
 * Re-aggregate the manager holdings for a subset of clients (empty = all).
 * R6: an unpriced symbol keeps value/P&L null and is left out of BOTH totals' cost and value.
 */
export function aggregateHoldings(
  holdings: ManagerHoldingsItem[],
  selected: ReadonlySet<string>,
): { rows: BookHoldingRow[]; totals: BookHoldingTotals } {
  const rows: BookHoldingRow[] = [];
  const totals: BookHoldingTotals = { invested: 0, marketValue: 0, unrealized: 0, returnPct: null, unpriced: 0 };
  for (const h of holdings) {
    const price = h.current_price ?? null;
    const picked = (h.clients ?? []).filter((c) => selected.size === 0 || selected.has(c.client_id));
    if (picked.length === 0) continue;
    const quantity = picked.reduce((s, c) => s + c.quantity, 0);
    const invested = picked.reduce((s, c) => s + c.invested, 0);
    const marketValue = price != null ? quantity * price : null;
    const unrealized = marketValue != null ? marketValue - invested : null;
    rows.push({
      symbol: h.symbol,
      exchange: h.exchange,
      price,
      priceAsOf: h.price_as_of ?? null,
      pricedOn: h.priced_on ?? null,
      quantity,
      invested,
      marketValue,
      unrealized,
      returnPct: unrealized != null && invested > 0 ? unrealized / invested : null,
      clients: picked.map((c) => ({ ...c, marketValue: price != null ? c.quantity * price : null })),
    });
    if (marketValue == null) {
      totals.unpriced += 1;
    } else {
      totals.invested += invested;
      totals.marketValue += marketValue;
    }
  }
  totals.unrealized = totals.marketValue - totals.invested;
  totals.returnPct = totals.invested > 0 ? totals.unrealized / totals.invested : null;
  rows.sort((a, b) => (b.marketValue ?? -1) - (a.marketValue ?? -1) || a.symbol.localeCompare(b.symbol));
  return { rows, totals };
}
