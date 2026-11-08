import React from 'react';
import { formatPercent, formatRupees, type ClientMetrics, type ClientSummary } from '@/lib/api';
import { MetricCard } from '@/components/MetricCard';

interface Props {
  overview: ClientSummary;
  metrics?: ClientMetrics;
  positionsCount: number;
}

/** R1 capital cards. R3: CAGR is null under 365 days — say so (checked with != null, R12). */
export const ClientHeadlineCards: React.FC<Props> = ({ overview, metrics, positionsCount }) => {
  const pnlPositive = (overview.total_pnl ?? 0) >= 0;
  const cagr = metrics?.cagr;
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <MetricCard
        title="Capital Deployed"
        value={formatRupees(overview.capital_deployed)}
        badge="Rule R1"
        subValue={`Current Invested: ${formatRupees(overview.current_invested)}`}
        tooltip="Peak cumulative net cash deployed in this portfolio"
      />
      <MetricCard title="Market Value" value={formatRupees(overview.market_value)} badge="Open Value" subValue={`${positionsCount} Open Holdings`} />
      <MetricCard
        title="Total P&L"
        value={formatRupees(overview.total_pnl)}
        badge={pnlPositive ? 'Gain' : 'Loss'}
        trend={pnlPositive ? 'positive' : 'negative'}
        subValue={`Realized: ${formatRupees(overview.realized_pnl)} · Unrealized: ${formatRupees(overview.unrealized_pnl)}`}
      />
      <MetricCard
        title="Return on Capital"
        value={formatPercent(overview.return_on_capital)}
        badge="Return %"
        trend={overview.return_on_capital >= 0 ? 'positive' : 'negative'}
        subValue={cagr != null ? `CAGR: ${formatPercent(cagr)}` : 'Under 1Y (Total Return shown)'}
      />
    </div>
  );
};
