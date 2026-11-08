import React, { useMemo } from 'react';
import { EChart } from '@/components/charts/EChart';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryStates';
import { formatPercent } from '@/lib/api';
import type { ClientReturnSeries } from '@/lib/apiAdmin';
import { axisStyle, token } from './chartTheme';
import { useClientReturns } from './useBook';

function options(clients: ClientReturnSeries[]) {
  const dates = Array.from(new Set(clients.flatMap((c) => c.series.map((p) => p.as_of)))).sort();
  const series = clients.map((c) => {
    const byDate = new Map(c.series.map((p) => [p.as_of, p.value]));
    return { name: c.name, type: 'line', showSymbol: false, connectNulls: true, data: dates.map((d) => byDate.get(d) ?? null) };
  });
  return {
    tooltip: { trigger: 'axis', valueFormatter: (v: number | null) => formatPercent(v) },
    legend: { type: 'scroll', textStyle: { color: token('subtle') } },
    grid: { left: 64, right: 16, top: 40, bottom: 40 },
    xAxis: { type: 'category', data: dates, ...axisStyle() },
    yAxis: { type: 'value', name: 'Return', ...axisStyle(), axisLabel: { ...axisStyle().axisLabel, formatter: (v: number) => formatPercent(v, 0) } },
    dataZoom: [{ type: 'inside' }],
    series,
  };
}

/** Each client's time-weighted % return, rebased to 0 — fair across very different account sizes. */
const ClientReturnsChart: React.FC<{ managerId: string }> = ({ managerId }) => {
  const q = useClientReturns(managerId);
  const opts = useMemo(() => (q.data?.length ? options(q.data) : null), [q.data]);
  if (q.isLoading) return <LoadingBlock rows={4} label="Loading client returns" />;
  if (q.isError) return <ErrorBlock message="Could not load client returns." onRetry={() => q.refetch()} />;
  if (!opts || !q.data) return <EmptyBlock title="No client NAV history yet" />;
  return (
    <div>
      <EChart options={opts} height={340} />
      <details className="mt-2 text-xs text-subtle">
        <summary className="cursor-pointer">Data table</summary>
        <table className="mt-2 w-full text-left" aria-label="Latest return per client">
          <thead>
            <tr><th className="py-1">Client</th><th className="py-1 text-right">Return to date</th></tr>
          </thead>
          <tbody>
            {q.data.map((c) => (
              <tr key={c.client_id}>
                <td className="py-1 text-ink">{c.name}</td>
                <td className="py-1 text-right font-mono">{formatPercent(c.series.at(-1)?.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
};

export default ClientReturnsChart;
