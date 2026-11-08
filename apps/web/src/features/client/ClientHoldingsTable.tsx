import React from 'react';
import { Briefcase } from 'lucide-react';
import { formatPercent, formatRupees, type PositionItem } from '@/lib/api';
import { EmptyBlock } from '@/components/QueryStates';
import { SymbolWithExchange } from '@/components/ExchangeBadge';
import { UnpricedNotice } from '@/features/client/UnpricedNotice';

interface Props {
  positions: PositionItem[];
  onSelect: (p: PositionItem) => void;
}

const HEAD = ['Symbol', 'Qty', 'Avg Cost', 'Invested Cost', 'Market Price', 'Current Value', 'Unrealized P&L', 'Return %'];

const Row: React.FC<{ p: PositionItem; onSelect: (p: PositionItem) => void }> = React.memo(({ p, onSelect }) => {
  const pnlCls = p.unrealized_pnl == null ? 'text-subtle' : p.unrealized_pnl >= 0 ? 'text-positive' : 'text-negative';
  const unpriced = p.priced === false; // R6: no price → no value, no P&L (never cost and 0 %)
  return (
    <tr
      className="hover:bg-canvas/50 transition-colors cursor-pointer focus:outline-none focus:bg-canvas"
      tabIndex={0}
      onClick={() => onSelect(p)}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onSelect(p))}
      aria-label={`Open ${p.symbol} details`}
    >
      <td className="py-3 px-4 font-medium text-ink">
        <SymbolWithExchange symbol={p.symbol} exchange={p.exchange} />
      </td>
      <td className="py-3 px-4 text-right font-mono text-xs text-ink">{p.quantity.toLocaleString('en-IN')}</td>
      <td className="py-3 px-4 text-right font-mono text-xs text-ink">{formatRupees(p.avg_cost)}</td>
      <td className="py-3 px-4 text-right font-mono text-xs text-ink">{formatRupees(p.invested)}</td>
      <td className="py-3 px-4 text-right font-mono text-xs text-ink font-semibold">
        {unpriced ? <span className="font-sans font-medium text-subtle" title="Excluded from market value and invested (R6)">No price</span> : formatRupees(p.current_price)}
        {!unpriced && p.priced_on && <span className="block font-sans text-[10px] font-normal text-subtle" title="No close on this lot's own exchange; valued at the other exchange's close (ADR-0009)">{p.priced_on} price</span>}
      </td>
      <td className="py-3 px-4 text-right font-mono text-xs text-ink font-semibold">{formatRupees(p.market_value)}</td>
      <td className={`py-3 px-4 text-right font-mono text-xs font-medium ${pnlCls}`}>{formatRupees(p.unrealized_pnl)}</td>
      <td className={`py-3 px-4 text-right font-mono text-xs font-medium ${pnlCls}`}>{formatPercent(p.return_pct)}</td>
    </tr>
  );
});
Row.displayName = 'HoldingRow';

export const ClientHoldingsTable: React.FC<Props> = ({ positions, onSelect }) => (
  <div className="bg-paper border border-hairline rounded-card overflow-hidden shadow-sm">
    <div className="p-5 border-b border-hairline flex items-center justify-between">
      <div className="flex items-center gap-2">
        <Briefcase className="w-5 h-5 text-subtle" aria-hidden />
        <h2 className="text-base font-semibold text-ink">Holdings & Positions</h2>
      </div>
      <span className="text-xs font-medium text-subtle bg-canvas px-2.5 py-1 rounded-full border border-hairline">
        {positions.length} Stocks · click a row for details
      </span>
    </div>
    <UnpricedNotice positions={positions} />
    {positions.length === 0 ? (
      <EmptyBlock title="No open positions held." />
    ) : (
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-sm" aria-label="Open positions">
          <thead>
            <tr className="bg-canvas/60 text-subtle text-xs border-b border-hairline">
              {HEAD.map((h, i) => (
                <th key={h} className={`py-3 px-4 font-semibold ${i > 0 ? 'text-right' : ''}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {positions.map((p) => (
              <Row key={`${p.security_id}-${p.exchange}`} p={p} onSelect={onSelect} />
            ))}
          </tbody>
        </table>
      </div>
    )}
  </div>
);
