import type { EChartsCoreOption } from 'echarts/core';
import { formatPercent, formatRupees } from '@/lib/api';
import type { AllocationBucket } from '@/lib/apiAnalytics';
import { axisStyle, chartTokens } from './chartTokens';

const MAX_BARS = 15;

/** Horizontal weight bars (largest first). The table below is the data fallback (a11y). */
export function allocationChartOptions(buckets: AllocationBucket[]): EChartsCoreOption {
  const t = chartTokens();
  const rows = buckets.slice(0, MAX_BARS).reverse();
  return {
    grid: { left: 8, right: 48, top: 8, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'item',
      formatter: (p: { dataIndex: number }) => {
        const b = rows[p.dataIndex];
        return `${b.key}<br/>${formatRupees(b.value, 0)} · ${formatPercent(b.weight)}`;
      },
    },
    xAxis: { type: 'value', ...axisStyle(t), axisLabel: { color: t.subtle, fontSize: 11, formatter: (v: number) => formatPercent(v, 0) } },
    yAxis: { type: 'category', data: rows.map((b) => b.key), ...axisStyle(t), splitLine: { show: false } },
    series: [
      {
        type: 'bar',
        data: rows.map((b) => b.weight ?? 0),
        itemStyle: { color: t.accent, borderRadius: [0, 6, 6, 0] },
        label: { show: true, position: 'right', color: t.subtle, fontSize: 10, formatter: (p: { value: number }) => formatPercent(p.value, 1) },
      },
    ],
  };
}
