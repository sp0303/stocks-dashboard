import React from 'react';
import { Trash2 } from 'lucide-react';
import { formatRupees } from '@/lib/api';
import type { DividendItem } from '@/lib/apiLedger';

interface Props {
  rows: DividendItem[];
  canEdit: boolean;
  busy: boolean;
  onDelete: (d: DividendItem) => void;
}

export const DividendsTable: React.FC<Props> = ({ rows, canEdit, busy, onDelete }) => (
    <div className="overflow-x-auto">
      <table className="w-full text-left border-collapse text-sm" aria-label="Dividend history">
        <thead>
          <tr className="bg-canvas/60 text-subtle text-xs border-b border-hairline">
            <th className="py-3 px-4 font-semibold">Ex-date</th>
            <th className="py-3 px-4 font-semibold">Symbol</th>
            <th className="py-3 px-4 font-semibold text-right">Per share</th>
            <th className="py-3 px-4 font-semibold text-right">Shares</th>
            <th className="py-3 px-4 font-semibold text-right">Amount</th>
            <th className="py-3 px-4 font-semibold">Source</th>
            {canEdit && <th className="py-3 px-4" aria-label="Actions" />}
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline">
          {rows.map((d) => (
            <tr key={d.dividend_id} className="hover:bg-canvas/50">
              <td className="py-3 px-4 text-xs font-mono text-subtle">{d.ex_date}</td>
              <td className="py-3 px-4 text-xs font-bold text-ink">{d.symbol}</td>
              <td className="py-3 px-4 text-right font-mono text-xs">{formatRupees(d.amount_per_share, 4)}</td>
              <td className="py-3 px-4 text-right font-mono text-xs">{d.quantity.toLocaleString('en-IN')}</td>
              <td className="py-3 px-4 text-right font-mono text-xs font-semibold">{formatRupees(d.amount)}</td>
              <td className="py-3 px-4 text-[11px] uppercase text-subtle">{d.source}</td>
              {canEdit && (
                <td className="py-3 px-4 text-right">
                  {d.source === 'manual' && (
                    <button
                      type="button"
                      onClick={() => onDelete(d)}
                      disabled={busy}
                      aria-label={`Delete ${d.symbol} dividend`}
                      className="p-1 rounded-interactive text-subtle hover:text-negative disabled:opacity-50"
                    >
                      <Trash2 className="w-3.5 h-3.5" aria-hidden />
                    </button>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
);
