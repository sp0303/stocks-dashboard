import React, { useMemo, useState } from 'react';
import { Activity } from 'lucide-react';
import { EChart } from '@/components/charts/EChart';
import type { Pool } from '@/lib/apiAnalytics';
import { POOLS } from './pools';
import { AnalyticsGate } from './AnalyticsGate';
import { Card } from './Card';
import { Segmented } from './Segmented';
import { TradeBreakdowns } from './TradeBreakdowns';
import { TradeStatGrid } from './TradeStatGrid';
import { equityCurveOptions } from './tradeChartOptions';
import { useTradeAnalytics } from './useAnalytics';

const TradeAnalyticsTab: React.FC<{ clientId: string }> = ({ clientId }) => {
  const [pool, setPool] = useState<Pool>('delivery');
  const q = useTradeAnalytics(clientId, pool);
  const a = q.data?.data;
  const curve = useMemo(() => (a ? equityCurveOptions(a) : {}), [a]);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Segmented label="Trade pool" value={pool} options={POOLS} onChange={setPool} />
        <span className="text-xs text-subtle">Matched shares only: sells without a known buy are excluded (R7).</span>
      </div>
      <AnalyticsGate isLoading={q.isLoading} error={q.error} onRetry={() => q.refetch()} empty={!a || a.closed_trades === 0} emptyTitle={`No closed ${pool} trades`}>
        {a && (
          <>
            <TradeStatGrid a={a} />
            <Card title="Equity curve (cumulative realised P&L)" icon={<Activity className="w-5 h-5 text-subtle" aria-hidden />}>
              <EChart options={curve} height={280} />
            </Card>
            <TradeBreakdowns a={a} />
          </>
        )}
      </AnalyticsGate>
    </div>
  );
};

export default TradeAnalyticsTab;
