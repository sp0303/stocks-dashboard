import React, { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { formatPercent, formatRupees } from '@/lib/api';
import type { BookHoldingRow } from './holdingsAggregate';

const NUM = 'py-3 px-4 text-right font-mono text-xs';
const sign = (v: number | null) => (v == null ? 'text-subtle' : v < 0 ? 'text-negative' : 'text-positive');

/** One symbol; expands to show which clients hold it. */
export const HoldingRow: React.FC<{ h: BookHoldingRow }> = React.memo(({ h }) => {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr className="hover:bg-canvas/50">
        <td className="py-3 px-4">
          <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="inline-flex items-center gap-1 font-bold font-mono text-ink text-xs">
            {open ? <ChevronDown className="w-3.5 h-3.5" aria-hidden /> : <ChevronRight className="w-3.5 h-3.5" aria-hidden />}
            {h.symbol}
          </button>
        </td>
        <td className={`${NUM} text-subtle`}>{h.clients.length}</td>
        <td className={NUM}>{h.quantity.toLocaleString('en-IN')}</td>
        <td className={NUM}>{formatRupees(h.invested)}</td>
        <td className={NUM} title={h.priceAsOf ? `${h.pricedOn ?? h.exchange} close of ${h.priceAsOf}${h.pricedOn ? ' (no close on its own exchange)' : ''}` : 'no price'}>{h.price != null ? formatRupees(h.price) : 'unpriced'}{h.pricedOn && <span className="ml-1 font-sans text-[10px] text-subtle">{h.pricedOn} price</span>}</td>
        <td className={`${NUM} font-semibold`}>{formatRupees(h.marketValue)}</td>
        <td className={`${NUM} ${sign(h.unrealized)}`}>{formatRupees(h.unrealized)}</td>
        <td className={`${NUM} ${sign(h.returnPct)}`}>{formatPercent(h.returnPct)}</td>
      </tr>
      {open &&
        h.clients.map((c) => (
          <tr key={c.client_id} className="bg-canvas/40 text-xs">
            <td className="py-2 px-4 pl-10 text-ink" colSpan={2}>{c.name}</td>
            <td className={NUM}>{c.quantity.toLocaleString('en-IN')}</td>
            <td className={NUM}>{formatRupees(c.invested)}</td>
            <td />
            <td className={NUM}>{formatRupees(c.marketValue)}</td>
            <td className={NUM} colSpan={2} />
          </tr>
        ))}
    </>
  );
});
HoldingRow.displayName = 'HoldingRow';
