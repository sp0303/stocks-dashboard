import React, { Suspense, lazy, useCallback, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  fetchClientOverview,
  fetchClientPositions,
  fetchClientSeries,
  fetchClientMetrics,
  fetchBenchmarkSeries,
  type ClientSummary,
  type PositionItem,
  type DailySeriesPoint,
  type ClientMetrics,
} from '@/lib/api';
import { EChart } from '@/components/charts/EChart';
import { LoadingBlock } from '@/components/QueryStates';
import { ArrowLeft, TrendingUp } from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import { ClientTradesTab } from './ClientTradesTab';
import { PnlCalendar } from './PnlCalendar';
import { ClientHeader } from './ClientHeader';
import { ClientHeadlineCards } from './ClientHeadlineCards';
import { ClientRiskStats } from './ClientRiskStats';
import { ClientHoldingsTable } from './ClientHoldingsTable';
import { ClientSubTabs, type ClientTab } from './ClientSubTabs';
import { buildNavChartOptions } from './navChartOptions';
import { AnalyticsTabPanel, OverviewExtras, isAnalyticsTab } from '@/features/client-analytics';

const DividendsTab = lazy(() => import('@/features/dividends/DividendsTab'));
const StockDetailDrawer = lazy(() => import('@/features/stock-detail/StockDetailDrawer'));

interface ClientViewProps {
  clientId: string;
  onBack: () => void;
}

export const ClientView: React.FC<ClientViewProps> = ({ clientId, onBack }) => {
  // All hooks run before any early return (React #310).
  const token = useAuthStore((s) => s.accessToken);
  const { data: overview, isLoading: loadingOverview } = useQuery<ClientSummary>({
    queryKey: ['client', clientId, 'overview', token],
    queryFn: () => fetchClientOverview(clientId, token),
  });
  const { data: positions, isLoading: loadingPositions } = useQuery<PositionItem[]>({
    queryKey: ['client', clientId, 'positions', token],
    queryFn: () => fetchClientPositions(clientId, token),
  });
  const { data: series, isLoading: loadingSeries } = useQuery<DailySeriesPoint[]>({
    queryKey: ['client', clientId, 'series', token],
    queryFn: () => fetchClientSeries(clientId, token),
  });
  const { data: metrics } = useQuery<ClientMetrics>({
    queryKey: ['client', clientId, 'metrics', token],
    queryFn: () => fetchClientMetrics(clientId, token),
  });

  const [clientTab, setClientTab] = useState<ClientTab>('positions');
  const [selected, setSelected] = useState<PositionItem | null>(null);
  const closeDrawer = useCallback(() => setSelected(null), []);

  const startDate = series && series.length > 0 ? series[0].as_of : undefined;
  const endDate = series && series.length > 0 ? series[series.length - 1].as_of : undefined;
  const { data: benchmarkSeries } = useQuery({
    queryKey: ['benchmarkSeries', '^NSEI', startDate, endDate],
    queryFn: () => fetchBenchmarkSeries('^NSEI', startDate, endDate, token),
    enabled: !!startDate && !!endDate,
  });

  const chartOptions = useMemo(() => buildNavChartOptions(series, benchmarkSeries), [series, benchmarkSeries]);

  if (loadingOverview || loadingPositions || loadingSeries) {
    return <LoadingBlock rows={5} label="Loading client" />;
  }

  if (!overview) {
    return (
      <div className="p-8">
        <button onClick={onBack} className="flex items-center gap-2 text-sm text-subtle hover:text-ink mb-4">
          <ArrowLeft className="w-4 h-4" /> Back to Manager Book
        </button>
        <div role="alert" className="p-4 text-negative border border-hairline rounded-card text-sm">Client not found.</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <ClientHeader clientId={clientId} overview={overview} onBack={onBack} />
      <ClientHeadlineCards overview={overview} metrics={metrics} positionsCount={positions?.length ?? 0} />
      {metrics && <ClientRiskStats metrics={metrics} />}
      <Suspense fallback={<LoadingBlock rows={2} label="Loading analytics" />}>
        <OverviewExtras clientId={clientId} />
      </Suspense>

      <div className="bg-paper border border-hairline rounded-card p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-subtle" aria-hidden />
            <h2 className="text-base font-semibold text-ink">Time-Weighted NAV Performance</h2>
          </div>
          <span className="text-xs text-subtle font-mono">Indexed to 100.0 (Rule R2)</span>
        </div>
        <EChart options={chartOptions} height={320} />
      </div>

      <ClientSubTabs active={clientTab} positionsCount={positions?.length ?? 0} onChange={setClientTab} />
      {clientTab === 'trades' && <ClientTradesTab clientId={clientId} />}
      {clientTab === 'calendar' && <PnlCalendar series={series || []} />}
      {clientTab === 'positions' && <ClientHoldingsTable positions={positions ?? []} onSelect={setSelected} />}
      {isAnalyticsTab(clientTab) && <AnalyticsTabPanel tab={clientTab} clientId={clientId} />}
      <Suspense fallback={<LoadingBlock rows={2} />}>
        {clientTab === 'dividends' && <DividendsTab clientId={clientId} />}
        {selected && <StockDetailDrawer clientId={clientId} position={selected} onClose={closeDrawer} />}
      </Suspense>
    </div>
  );
};
