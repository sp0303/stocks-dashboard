import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { formatRupees } from '@/lib/api';
import { fetchPlatformOverview } from '@/lib/apiAdmin';
import { MetricCard } from '@/components/MetricCard';
import { ErrorBlock, LoadingBlock } from '@/components/QueryStates';

const count = (n: number) => n.toLocaleString('en-IN');

/** Platform tiles: active managers, active clients, trades stored, AUM and P&L. */
export const PlatformTiles: React.FC = () => {
  const q = useQuery({ queryKey: ['admin', 'overview'], queryFn: fetchPlatformOverview });
  if (q.isLoading) return <LoadingBlock rows={1} label="Loading platform totals" />;
  if (q.isError || !q.data) return <ErrorBlock message="Could not load platform totals." onRetry={() => q.refetch()} />;
  const o = q.data;
  return (
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
      <MetricCard title="Managers" value={count(o.manager_count)} subValue="active" />
      <MetricCard title="Clients" value={count(o.client_count)} subValue="active portfolios" />
      <MetricCard title="Trades stored" value={count(o.trade_count)} subValue="in the ledger" />
      <MetricCard title="Platform AUM" value={formatRupees(o.total_market_value, 0)} subValue={`Capital deployed ${formatRupees(o.total_capital_deployed, 0)}`} />
      <MetricCard
        title="Platform P&L"
        value={formatRupees(o.total_pnl, 0)}
        trend={o.total_pnl < 0 ? 'negative' : 'positive'}
        subValue={o.total_pnl < 0 ? 'Loss · realised + unrealised' : 'Gain · realised + unrealised'}
      />
    </div>
  );
};
