import React from 'react';
import { formatRate, formatRupees } from '@/lib/api';
import type { BucketRow } from '@/lib/apiAnalytics';

export const BucketTable: React.FC<{ rows: BucketRow[]; caption: string; label: string }> = ({ rows, caption, label }) => (
  <div className="overflow-x-auto max-h-72">
    <table className="w-full text-sm" aria-label={caption}>
      <thead className="text-[11px] uppercase text-subtle sticky top-0 bg-paper">
        <tr>
          <th scope="col" className="text-left py-2 pr-3">{label}</th>
          <th scope="col" className="text-right py-2 pr-3">Trades</th>
          <th scope="col" className="text-right py-2 pr-3">Win rate</th>
          <th scope="col" className="text-right py-2">P&amp;L</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.bucket} className="border-t border-hairline">
            <td className="py-1.5 pr-3 text-ink">{r.bucket}</td>
            <td className="py-1.5 pr-3 text-right font-mono text-ink">{r.trades}</td>
            <td className="py-1.5 pr-3 text-right font-mono text-ink">{formatRate(r.win_rate, 1)}</td>
            <td className={`py-1.5 text-right font-mono ${r.pnl < 0 ? 'text-negative' : 'text-ink'}`}>{formatRupees(r.pnl, 0)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);
