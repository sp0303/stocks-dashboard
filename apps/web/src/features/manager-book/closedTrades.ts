import type { ClosedTrade } from '@/lib/apiAdmin';

export const SORTS = {
  recent: { label: 'Most recent', key: 'sell_date', dir: -1 },
  account: { label: 'Account (A–Z)', key: 'client_name', dir: 1 },
  stock: { label: 'Stock (A–Z)', key: 'symbol', dir: 1 },
  pnl_hi: { label: 'P&L (high → low)', key: 'pnl', dir: -1 },
  pnl_lo: { label: 'P&L (low → high)', key: 'pnl', dir: 1 },
} as const;
export type SortId = keyof typeof SORTS;

/** Filter by account and symbol substring, then sort (v1 ManagerTradeLog presets). */
export function viewClosedTrades(rows: ClosedTrade[], account: string, symbol: string, sort: SortId): ClosedTrade[] {
  const s = SORTS[sort] ?? SORTS.recent;
  const sym = symbol.trim().toUpperCase();
  return rows
    .filter((r) => (!account || r.client_id === account) && (!sym || r.symbol.includes(sym)))
    .sort((a, b) => {
      const x = a[s.key];
      const y = b[s.key];
      const c = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'en', { sensitivity: 'base' });
      return c * s.dir;
    });
}
