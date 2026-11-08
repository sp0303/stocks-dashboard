import type { ManagerHoldingsItem } from '@/lib/api';
import type { PriceQuote } from '@/lib/apiResearch';

export type Lane = 'watching' | 'holding' | 'exit';

/** Decimal change of price vs the planned entry (R12: decimals; UI formats). null when unknown. */
export function pctVsEntry(price: number | null | undefined, entry: number | null | undefined): number | null {
  if (price == null || entry == null || entry === 0) return null;
  return (price - entry) / entry;
}

/** Key used for price lookups: the API echoes the requested spelling, trimmed + upper-cased. */
export function symbolKey(symbol: string): string {
  return symbol.trim().toUpperCase();
}

export function priceMap(closes: PriceQuote[] | undefined): Map<string, PriceQuote> {
  return new Map((closes ?? []).map((c) => [symbolKey(c.symbol), c]));
}

/** Decimal distance from price up/down to an alert level; null when either is unknown. */
export function pctToAlert(price: number | null | undefined, alert: number | null | undefined): number | null {
  if (price == null || alert == null || price === 0) return null;
  return (alert - price) / price;
}

/**
 * Re-total a holding for the selected clients. `selected === null` means "all clients".
 * Unpriced holdings keep value/P&L null (R6) instead of falling back to cost.
 */
export function holdingForClients(
  h: ManagerHoldingsItem,
  selected: Set<string> | null,
): ManagerHoldingsItem | null {
  if (selected === null) return h;
  const rows = (h.clients ?? []).filter((c) => selected.has(c.client_id));
  if (rows.length === 0) return null;
  const quantity = rows.reduce((s, c) => s + c.quantity, 0);
  const invested = rows.reduce((s, c) => s + c.invested, 0);
  const price = h.current_price ?? null;
  const market_value = price != null ? quantity * price : null;
  const unrealized_pnl = market_value != null ? market_value - invested : null;
  return {
    ...h,
    clients: rows,
    client_count: rows.length,
    quantity,
    invested,
    avg_cost: quantity > 0 ? invested / quantity : 0,
    market_value,
    unrealized_pnl,
    return_pct: unrealized_pnl != null && invested > 0 ? unrealized_pnl / invested : null,
  };
}

/** Unique clients across holdings, for the filter chips. */
export function clientsOf(holdings: ManagerHoldingsItem[] | undefined): { id: string; name: string }[] {
  const seen = new Map<string, string>();
  for (const h of holdings ?? []) for (const c of h.clients ?? []) seen.set(c.client_id, c.name);
  return [...seen].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name));
}

/** Card colours are design tokens, never raw hex (frontend rule 9). Unknown values render plain. */
export const CARD_COLOURS: Record<string, string> = {
  mint: 'bg-emerald-50 border-emerald-200',
  sky: 'bg-sky-50 border-sky-200',
  amber: 'bg-amber-50 border-amber-200',
  rose: 'bg-rose-50 border-rose-200',
  violet: 'bg-violet-50 border-violet-200',
};

export function colourClass(colour: string | null | undefined): string {
  return (colour && CARD_COLOURS[colour]) || 'bg-paper border-hairline';
}
