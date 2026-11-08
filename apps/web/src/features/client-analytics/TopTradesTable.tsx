import React from 'react';
import { formatPercent, formatRupees } from '@/lib/api';
import type { TopTrade } from '@/lib/apiAnalytics';

export const TopTradesTable: React.FC<{ rows: TopTrade[]; caption: string }> = ({ rows, caption }) =>
  rows.length === 0 ? (
    <p className="text-xs text-subtle py-4">None.</p>
  ) : (
    <table className="w-full text-sm" aria-label={caption}>
      <thead className="text-[11px] uppercase text-subtle">
        <tr>
          <th scope="col" className="text-left py-2 pr-3">Stock</th>
          <th scope="col" className="text-left py-2 pr-3">Exit</th>
          <th scope="col" className="text-right py-2 pr-3">Days</th>
          <th scope="col" className="text-right py-2 pr-3">Return</th>
          <th scope="col" className="text-right py-2">P&amp;L</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={`${r.symbol}-${r.sell_date}-${i}`} className="border-t border-hairline">
            <td className="py-1.5 pr-3 font-semibold text-ink">{r.symbol}</td>
            <td className="py-1.5 pr-3 text-subtle">{r.sell_date}</td>
            <td className="py-1.5 pr-3 text-right font-mono text-ink">{r.holding_days.toFixed(0)}</td>
            <td className="py-1.5 pr-3 text-right font-mono text-ink">{formatPercent(r.pnl_pct)}</td>
            <td className={`py-1.5 text-right font-mono ${r.pnl < 0 ? 'text-negative' : 'text-ink'}`}>{formatRupees(r.pnl, 0)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
