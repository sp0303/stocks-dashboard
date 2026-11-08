import type { EChartsCoreOption } from 'echarts/core';
import { formatRupees } from '@/lib/api';
import type { BucketRow, TradeAnalytics } from '@/lib/apiAnalytics';
import { axisStyle, chartTokens } from './chartTokens';

const rupeeAxis = (v: number) => formatRupees(v, 0);

/** Cumulative realised P&L by exit date, with the drawdown band below zero. */
export function equityCurveOptions(a: TradeAnalytics): EChartsCoreOption {
  const t = chartTokens();
  return {
    legend: { textStyle: { color: t.subtle }, top: 0 },
    tooltip: { trigger: 'axis', valueFormatter: (v: number) => formatRupees(v, 0) },
    grid: { left: 8, right: 16, top: 32, bottom: 16, containLabel: true },
    xAxis: { type: 'category', data: a.equity_curve.map((p) => p.date), ...axisStyle(t), splitLine: { show: false } },
    yAxis: { type: 'value', ...axisStyle(t), axisLabel: { color: t.subtle, fontSize: 11, formatter: rupeeAxis } },
    series: [
      { name: 'Cumulative realised P&L', type: 'line', data: a.equity_curve.map((p) => p.cum_pnl), symbol: 'none', lineStyle: { color: t.ink, width: 2 } },
      {
        name: 'Drawdown', type: 'line', data: a.equity_curve.map((p) => p.drawdown), symbol: 'none',
        lineStyle: { color: t.negative, width: 1 }, areaStyle: { color: t.negative, opacity: 0.15 },
      },
    ],
  };
}

/** P&L per bucket (bars coloured by sign: ember only for negatives). */
export function bucketBarOptions(rows: BucketRow[]): EChartsCoreOption {
  const t = chartTokens();
  return {
    tooltip: { trigger: 'axis', valueFormatter: (v: number) => formatRupees(v, 0) },
    grid: { left: 8, right: 16, top: 16, bottom: 16, containLabel: true },
    xAxis: { type: 'category', data: rows.map((r) => r.bucket), ...axisStyle(t), splitLine: { show: false } },
    yAxis: { type: 'value', ...axisStyle(t), axisLabel: { color: t.subtle, fontSize: 11, formatter: rupeeAxis } },
    series: [
      {
        name: 'P&L', type: 'bar',
        data: rows.map((r) => ({ value: r.pnl, itemStyle: { color: r.pnl < 0 ? t.negative : t.positive } })),
      },
    ],
  };
}
