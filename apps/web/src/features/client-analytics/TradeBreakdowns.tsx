import React, { useMemo } from 'react';
import { EChart } from '@/components/charts/EChart';
import type { TradeAnalytics } from '@/lib/apiAnalytics';
import { BucketTable } from './BucketTable';
import { Card } from './Card';
import { TopTradesTable } from './TopTradesTable';
import { bucketBarOptions } from './tradeChartOptions';

/** Distribution, monthly, weekday and holding-period breakdowns + top winners/losers. */
export const TradeBreakdowns: React.FC<{ a: TradeAnalytics }> = ({ a }) => {
  const distOpts = useMemo(() => bucketBarOptions(a.distribution), [a]);
  const monthOpts = useMemo(() => bucketBarOptions(a.monthly), [a]);
  return (
    <>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="P&L distribution (return on cost)">
          <EChart options={distOpts} height={220} />
          <BucketTable rows={a.distribution} caption="P&L distribution" label="Return" />
        </Card>
        <Card title="Monthly realised P&L">
          <EChart options={monthOpts} height={220} />
          <BucketTable rows={a.monthly} caption="Monthly P&L" label="Month" />
        </Card>
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="By exit weekday"><BucketTable rows={a.by_weekday} caption="By exit weekday" label="Day" /></Card>
        <Card title="By holding period"><BucketTable rows={a.by_holding} caption="By holding period" label="Held" /></Card>
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Top winners"><TopTradesTable rows={a.top_winners} caption="Top winners" /></Card>
        <Card title="Top losers"><TopTradesTable rows={a.top_losers} caption="Top losers" /></Card>
      </div>
    </>
  );
};
