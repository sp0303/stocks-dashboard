import React from 'react';
import { formatPercent, formatRupees, type PositionItem } from '@/lib/api';

interface Props {
  position: PositionItem;
}

const Stat: React.FC<{ label: string; value: string; tone?: 'pos' | 'neg' }> = ({ label, value, tone }) => (
  <div className="bg-canvas border border-hairline rounded-interactive p-3">
    <div className="text-[11px] font-semibold uppercase text-subtle">{label}</div>
    <div className={`text-sm font-bold font-mono mt-0.5 ${tone === 'pos' ? 'text-positive' : tone === 'neg' ? 'text-negative' : 'text-ink'}`}>
      {value}
    </div>
  </div>
);

/** Open position + unrealised P&L for one symbol (values come from the portfolio engine, not recomputed here). */
export const PositionSummary: React.FC<Props> = ({ position: p }) => {
  const pnl = p.unrealized_pnl;
  const tone = pnl == null ? undefined : pnl >= 0 ? 'pos' : 'neg';
  return (
    <div className="grid grid-cols-2 gap-2">
      <Stat label="Quantity" value={p.quantity.toLocaleString('en-IN')} />
      <Stat label="Avg cost" value={formatRupees(p.avg_cost)} />
      <Stat label="Invested" value={formatRupees(p.invested)} />
      <Stat label="Last price" value={p.priced === false ? 'No price (excluded, R6)' : formatRupees(p.current_price)} />
      <Stat label="Market value" value={formatRupees(p.market_value)} />
      <Stat label="Unrealised P&L" value={`${formatRupees(pnl)} (${formatPercent(p.return_pct)})`} tone={tone} />
      {p.entry_date && <Stat label="Entry date" value={p.entry_date} />}
    </div>
  );
};
