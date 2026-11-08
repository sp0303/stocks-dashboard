import type { EChartsCoreOption } from 'echarts/core';
import { formatRupees } from '@/lib/api';
import type { BenchmarkTrack, Performance } from '@/lib/apiAnalytics';
import { axisStyle, chartTokens } from './chartTokens';

const rupeeAxis = (v: number) => formatRupees(v, 0);

/** Portfolio P&L vs benchmark P&L on the SAME net_invested baseline (R10). Null = gap, never a flat line. */
export function pnlVsBenchmarkOptions(p: Performance, bench: BenchmarkTrack | undefined): EChartsCoreOption {
  const t = chartTokens();
  const series: object[] = [
    { name: 'Portfolio P&L', type: 'line', data: p.portfolio_pnl, symbol: 'none', lineStyle: { color: t.ink, width: 2 } },
  ];
  if (bench) {
    series.push({
      name: `${bench.label} P&L`, type: 'line', data: bench.pnl, symbol: 'none', connectNulls: false,
      lineStyle: { color: t.subtle, width: 1.5, type: 'dashed' },
    });
  }
  return {
    legend: { textStyle: { color: t.subtle }, top: 0 },
    tooltip: { trigger: 'axis', valueFormatter: (v: number | null) => (v == null ? 'no data' : formatRupees(v, 0)) },
    grid: { left: 8, right: 16, top: 32, bottom: 40, containLabel: true },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 8 }],
    xAxis: { type: 'category', data: p.dates, ...axisStyle(t), splitLine: { show: false } },
    yAxis: { type: 'value', scale: true, ...axisStyle(t), axisLabel: { color: t.subtle, fontSize: 11, formatter: rupeeAxis } },
    series,
  };
}

/** Portfolio growth: market value against net invested (the money put in). */
export function growthOptions(p: Performance): EChartsCoreOption {
  const t = chartTokens();
  return {
    legend: { textStyle: { color: t.subtle }, top: 0 },
    tooltip: { trigger: 'axis', valueFormatter: (v: number) => formatRupees(v, 0) },
    grid: { left: 8, right: 16, top: 32, bottom: 16, containLabel: true },
    xAxis: { type: 'category', data: p.dates, ...axisStyle(t), splitLine: { show: false } },
    yAxis: { type: 'value', scale: true, ...axisStyle(t), axisLabel: { color: t.subtle, fontSize: 11, formatter: rupeeAxis } },
    series: [
      { name: 'Market value', type: 'line', data: p.market_value, symbol: 'none', lineStyle: { color: t.accent, width: 2 } },
      { name: 'Net invested', type: 'line', data: p.net_invested, symbol: 'none', step: 'end', lineStyle: { color: t.subtle, width: 1.5 } },
    ],
  };
}
