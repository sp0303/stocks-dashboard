import React, { useMemo, useState } from 'react';
import { EChart } from '@/components/charts/EChart';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryStates';
import { formatRupees } from '@/lib/api';
import type { BookPerformance } from '@/lib/apiAdmin';
import { axisStyle, token } from './chartTheme';
import { useBookPerformance } from './useBook';

function options(p: BookPerformance, shown: Set<string>) {
  const series = [
    { name: 'Whole book', type: 'line', showSymbol: false, data: p.book_pnl, lineStyle: { width: 2.5, color: token('accent') }, itemStyle: { color: token('accent') } },
    ...p.benchmarks
      .filter((b) => shown.has(b.code))
      .map((b) => ({ name: b.label, type: 'line', showSymbol: false, data: b.points, lineStyle: { width: 1.5, type: 'dashed' } })),
  ];
  return {
    tooltip: { trigger: 'axis', valueFormatter: (v: number | null) => (v == null ? '—' : formatRupees(v, 0)) },
    legend: { textStyle: { color: token('subtle') } },
    grid: { left: 80, right: 16, top: 40, bottom: 40 },
    xAxis: { type: 'category', data: p.dates, ...axisStyle() },
    yAxis: { type: 'value', name: 'Profit / loss (₹)', ...axisStyle(), axisLabel: { ...axisStyle().axisLabel, formatter: (v: number) => formatRupees(v, 0) } },
    dataZoom: [{ type: 'inside' }],
    series,
  };
}

/** Book P&L (value − net invested) vs index-units benchmarks on the same baseline (R10). */
const BookPerformanceChart: React.FC<{ managerId: string }> = ({ managerId }) => {
  const q = useBookPerformance(managerId);
  const [shown, setShown] = useState<Set<string> | null>(null);
  const active = useMemo(() => shown ?? new Set((q.data?.benchmarks ?? []).slice(0, 2).map((b) => b.code)), [shown, q.data]);
  const opts = useMemo(() => (q.data ? options(q.data, active) : null), [q.data, active]);

  if (q.isLoading) return <LoadingBlock rows={4} label="Loading book performance" />;
  if (q.isError || !q.data) return <ErrorBlock message="Could not load book performance." onRetry={() => q.refetch()} />;
  if (q.data.dates.length === 0) return <EmptyBlock title="No book history yet" hint="The portfolio worker has not built this manager's daily series." />;

  const toggle = (code: string) => {
    const next = new Set(active);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    setShown(next);
  };
  const stale = q.data.benchmarks.filter((b) => b.stale && active.has(b.code));
  return (
    <div className="space-y-3">
      <fieldset className="flex flex-wrap gap-4 text-xs text-ink">
        <legend className="sr-only">Benchmarks to compare</legend>
        {q.data.benchmarks.map((b) => (
          <label key={b.code} className="inline-flex items-center gap-1.5 cursor-pointer">
            <input type="checkbox" checked={active.has(b.code)} onChange={() => toggle(b.code)} /> {b.label}
          </label>
        ))}
      </fieldset>
      {stale.map((b) => (
        <p key={b.code} role="alert" className="text-xs text-negative border border-negative/30 bg-negative/5 p-2 rounded-interactive">
          {b.label} is stale: last value {b.last_date ?? 'never'}, {b.sessions_behind} sessions behind. The line stops there instead of flatlining.
        </p>
      ))}
      {opts && <EChart options={opts} height={340} />}
    </div>
  );
};

export default BookPerformanceChart;
