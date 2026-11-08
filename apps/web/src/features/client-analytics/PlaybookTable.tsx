import React from 'react';
import { formatPercent, formatRupees } from '@/lib/api';
import type { PlaybookRow } from '@/lib/apiAnalytics';

const COLS = ['Stock', 'Trades', 'Qty', 'Avg buy', 'Avg sell', 'Avg days', 'P&L', 'P&L %', 'Reason / notes'];

const Row: React.FC<{ r: PlaybookRow }> = React.memo(({ r }) => (
  <tr className="border-t border-hairline">
    <td className="py-1.5 pr-3 font-semibold text-ink">{r.symbol}</td>
    <td className="py-1.5 pr-3 text-right font-mono text-ink">{r.trades}</td>
    <td className="py-1.5 pr-3 text-right font-mono text-ink">{r.quantity.toLocaleString('en-IN')}</td>
    <td className="py-1.5 pr-3 text-right font-mono text-ink">{formatRupees(r.avg_buy_price)}</td>
    <td className="py-1.5 pr-3 text-right font-mono text-ink">{formatRupees(r.avg_sell_price)}</td>
    <td className="py-1.5 pr-3 text-right font-mono text-ink">{r.avg_days != null ? r.avg_days.toFixed(1) : '—'}</td>
    <td className={`py-1.5 pr-3 text-right font-mono ${r.pnl < 0 ? 'text-negative' : 'text-ink'}`}>{formatRupees(r.pnl, 0)}</td>
    <td className={`py-1.5 pr-3 text-right font-mono ${(r.pnl_pct ?? 0) < 0 ? 'text-negative' : 'text-ink'}`}>{formatPercent(r.pnl_pct)}</td>
    <td className="py-1.5 text-subtle max-w-xs truncate" title={r.reason}>{r.reason || '—'}</td>
  </tr>
));
Row.displayName = 'PlaybookRow';

/** One row per stock. Bounded height with sticky header; rows memoised. */
export const PlaybookTable: React.FC<{ rows: PlaybookRow[] }> = ({ rows }) => (
  <div className="overflow-auto max-h-[32rem]">
    <table className="w-full text-sm" aria-label="Playbook by stock">
      <thead className="text-[11px] uppercase text-subtle sticky top-0 bg-paper">
        <tr>
          {COLS.map((c, i) => (
            <th key={c} scope="col" className={`py-2 pr-3 ${i === 0 || i === COLS.length - 1 ? 'text-left' : 'text-right'}`}>{c}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => <Row key={`${r.symbol}-${r.exchange}`} r={r} />)}
      </tbody>
    </table>
  </div>
);
