import React from 'react';
import { PenLine } from 'lucide-react';
import { formatRupees } from '@/lib/api';
import type { ManualTrade } from '@/lib/apiAnalytics';
import { Card } from './Card';

/** Opening / adjustment trades entered by hand (source = manual). Renders nothing when there are none. */
export const ManualTradesCard: React.FC<{ rows: ManualTrade[] }> = ({ rows }) =>
  rows.length === 0 ? null : (
    <Card title={`Manual / adjustment trades (${rows.length})`} icon={<PenLine className="w-5 h-5 text-subtle" aria-hidden />}>
      <div className="overflow-x-auto max-h-64">
        <table className="w-full text-sm" aria-label="Manual trades">
          <thead className="text-[11px] uppercase text-subtle sticky top-0 bg-paper">
            <tr>
              {['Date', 'Stock', 'Side', 'Qty', 'Price', 'Note'].map((c) => (
                <th key={c} scope="col" className="text-left py-2 pr-3">{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.trade_id} className="border-t border-hairline">
                <td className="py-1.5 pr-3 text-subtle">{r.trade_date}</td>
                <td className="py-1.5 pr-3 font-semibold text-ink">{r.symbol}</td>
                <td className="py-1.5 pr-3 text-ink">{r.side}</td>
                <td className="py-1.5 pr-3 font-mono text-ink">{r.quantity}</td>
                <td className="py-1.5 pr-3 font-mono text-ink">{formatRupees(r.price)}</td>
                <td className="py-1.5 text-subtle">{r.note || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
