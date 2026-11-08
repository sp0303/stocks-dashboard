import React from 'react';
import { formatPercent, formatRupees } from '@/lib/api';
import type { BookSummary } from '@/lib/apiAdmin';
import { StatTile } from './StatTile';

const tone = (v?: number | null) => (v == null ? 'neutral' : v < 0 ? 'down' : 'up');
const rs = (v?: number | null) => formatRupees(v, 0);

/** v1 book tiles: totals are sums of each client's engine overview (R5); return on capital deployed (R1). */
export const BookTiles: React.FC<{ s: BookSummary }> = ({ s }) => {
  const t = s.totals;
  const i = s.insights;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3">
        <StatTile
          label="Total P&L"
          value={rs(t.total_pnl)}
          tone={tone(t.total_pnl)}
          sub={t.return_on_capital != null ? `${formatPercent(t.return_on_capital)} return` : 'return n/a (no capital)'}
        />
        <StatTile label="Book market value" value={rs(t.market_value)} sub={formatRupees(t.market_value)} />
        <StatTile
          label="Capital deployed"
          value={rs(t.capital_deployed)}
          sub="real investment"
          title="Peak of each client's own money tied up at once, summed per client. Reinvested profit is not counted again."
        />
        <StatTile label="Current invested" value={rs(t.current_invested)} sub="cost of what is held" />
        <StatTile label="Realised" value={rs(t.realized_pnl)} tone={tone(t.realized_pnl)} />
        <StatTile label="Unrealised" value={rs(t.unrealized_pnl)} tone={tone(t.unrealized_pnl)} />
        <StatTile label="Clients / stocks" value={`${t.client_count} / ${i.unique_stocks}`} />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatTile label="Most invested" value={i.most_invested?.symbol ?? '—'} sub={i.most_invested ? rs(i.most_invested.value) : undefined} />
        <StatTile label="Most traded" value={i.most_traded?.symbol ?? '—'} sub={i.most_traded ? `${i.most_traded.value} trades` : undefined} />
        <StatTile label="Top holding" value={i.top_holding?.symbol ?? '—'} sub={i.top_holding ? rs(i.top_holding.value) : undefined} />
        <StatTile label="Best performer" value={i.best_performer?.symbol ?? '—'} tone="up" sub={i.best_performer ? formatPercent(i.best_performer.value) : undefined} />
        <StatTile label="Worst performer" value={i.worst_performer?.symbol ?? '—'} tone="down" sub={i.worst_performer ? formatPercent(i.worst_performer.value) : undefined} />
      </div>
      {i.unpriced_symbols.length > 0 && (
        <p className="text-xs text-subtle">
          Unpriced (left out of cost and value, R6): {i.unpriced_symbols.join(', ')}
        </p>
      )}
    </div>
  );
};
