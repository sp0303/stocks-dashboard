import React, { useMemo, useState } from 'react';
import { LineChart } from 'lucide-react';
import { EChart } from '@/components/charts/EChart';
import { formatPercent, formatRupees } from '@/lib/api';
import { AnalyticsGate } from './AnalyticsGate';
import { BenchmarkPicker } from './BenchmarkPicker';
import { Card } from './Card';
import { StaleBenchmarkBanner } from './StaleBenchmarkBanner';
import { Stat, toneOf } from './Stat';
import { growthOptions, pnlVsBenchmarkOptions } from './performanceChartOptions';
import { useAnalyticsPerformance } from './useAnalytics';

const PerformanceTab: React.FC<{ clientId: string }> = ({ clientId }) => {
  const q = useAnalyticsPerformance(clientId);
  const p = q.data?.data;
  const [code, setCode] = useState<string | null>(null);
  const bench = p?.benchmarks.find((b) => b.code === code) ?? p?.benchmarks[0];
  const pnlOpts = useMemo(() => (p ? pnlVsBenchmarkOptions(p, bench) : {}), [p, bench]);
  const growthOpts = useMemo(() => (p ? growthOptions(p) : {}), [p]);
  const last = p && p.dates.length ? p.dates.length - 1 : -1;
  const benchPnl = bench && last >= 0 ? bench.pnl[last] : null;
  const picker = p && p.benchmarks.length > 0 && bench
    ? <BenchmarkPicker benchmarks={p.benchmarks} value={bench.code} onChange={setCode} />
    : null;
  return (
    <AnalyticsGate isLoading={q.isLoading} error={q.error} onRetry={() => q.refetch()} empty={!p || p.dates.length === 0} emptyTitle="No daily series yet">
      {p && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Stat label="TWR total return" value={formatPercent(p.total_return)} tone={toneOf(p.total_return)} />
            <Stat label="CAGR" value={p.cagr != null ? formatPercent(p.cagr) : '—'} hint={p.cagr != null ? 'Annualised (TWR)' : 'Shown only after 365 days (R3)'} tone={toneOf(p.cagr)} />
            <Stat label="Portfolio P&L" value={formatRupees(p.portfolio_pnl[last], 0)} tone={toneOf(p.portfolio_pnl[last])} />
            <Stat label={bench ? `${bench.label} P&L` : 'Benchmark P&L'} value={benchPnl != null ? formatRupees(benchPnl, 0) : '—'} hint="Same money, same dates, in the index" tone={toneOf(benchPnl)} />
          </div>
          <Card title="P&L vs benchmark" icon={<LineChart className="w-5 h-5 text-subtle" aria-hidden />} actions={picker}>
            {bench ? <StaleBenchmarkBanner bench={bench} /> : <p className="mb-3 text-xs text-subtle">No benchmark configured.</p>}
            <EChart options={pnlOpts} height={320} />
          </Card>
          <Card title="Portfolio growth">
            <EChart options={growthOpts} height={260} />
          </Card>
        </div>
      )}
    </AnalyticsGate>
  );
};

export default PerformanceTab;
