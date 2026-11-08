import React from 'react';
import { ArrowUpRight, Pencil, Trash2 } from 'lucide-react';
import { formatPercent, formatRupees } from '@/lib/api';
import type { BookRosterItem } from '@/lib/apiAdmin';

export type RosterAction = 'open' | 'edit' | 'delete';

const NUM = 'py-3 px-4 text-right font-mono text-xs';
const BTN = 'p-1.5 rounded-interactive text-subtle hover:text-ink hover:bg-canvas';
const sign = (v?: number | null) => (v == null ? 'text-subtle' : v < 0 ? 'text-negative' : 'text-positive');

export const RosterRow: React.FC<{ c: BookRosterItem; onAction: (a: RosterAction, c: BookRosterItem) => void }> = React.memo(({ c, onAction }) => (
  <tr className="hover:bg-canvas/50 cursor-pointer" onClick={() => onAction('open', c)}>
    <td className="py-3 px-4 font-medium text-ink">
      {c.name}
      {!c.computed && <span className="ml-2 text-[11px] text-subtle">(not computed yet)</span>}
    </td>
    <td className="py-3 px-4 text-subtle text-xs">{[c.broker, c.client_code].filter(Boolean).join(' · ') || '—'}</td>
    <td className={NUM}>{formatRupees(c.capital_deployed, 0)}</td>
    <td className={NUM}>{formatRupees(c.current_invested, 0)}</td>
    <td className={`${NUM} font-semibold`}>{formatRupees(c.market_value, 0)}</td>
    <td className={`${NUM} ${sign(c.total_pnl)}`}>{formatRupees(c.total_pnl, 0)}</td>
    <td className={`${NUM} ${sign(c.return_on_capital)}`}>{formatPercent(c.return_on_capital)}</td>
    <td className={`${NUM} text-subtle`}>{c.trade_count.toLocaleString('en-IN')}</td>
    <td className="py-3 px-4" onClick={(e) => e.stopPropagation()}>
      <div className="flex justify-end gap-1">
        <button type="button" className={BTN} aria-label={`Edit ${c.name}`} title="Edit" onClick={() => onAction('edit', c)}>
          <Pencil className="w-4 h-4" />
        </button>
        <button type="button" className={`${BTN} hover:text-negative`} aria-label={`Delete ${c.name}`} title="Delete" onClick={() => onAction('delete', c)}>
          <Trash2 className="w-4 h-4" />
        </button>
        <button type="button" className={BTN} aria-label={`Open ${c.name}`} title="Open dashboard" onClick={() => onAction('open', c)}>
          <ArrowUpRight className="w-4 h-4" />
        </button>
      </div>
    </td>
  </tr>
));
RosterRow.displayName = 'RosterRow';
