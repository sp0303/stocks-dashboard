import type { EChartsCoreOption } from 'echarts/core';
import type { BenchmarkSeriesPoint, DailySeriesPoint } from '@/lib/api';

/** ECharts options for the TWR NAV curve vs benchmark (Rule R2; R10 index-units, base 100). */
export function buildNavChartOptions(
  series: DailySeriesPoint[] | undefined,
  benchmarkSeries: BenchmarkSeriesPoint[] | undefined
): EChartsCoreOption {
  if (!series || series.length === 0) {
    return {
      title: { text: 'No performance series data', left: 'center', top: 'center' },
    };
  }

  const dates = series.map((s) => s.as_of);
  const navValues = series.map((s) => parseFloat(s.nav.toFixed(2)));

  // Index-units method (Rule R10): benchmark indexed to 100.0 on base date
  const bmMap = new Map<string, number>();
  if (benchmarkSeries && benchmarkSeries.length > 0) {
    const baseVal = benchmarkSeries[0].value;
    for (const pt of benchmarkSeries) {
      if (baseVal > 0) {
        bmMap.set(pt.as_of, parseFloat(((pt.value / baseVal) * 100.0).toFixed(2)));
      }
    }
  }

  let lastBm = 100.0;
  const benchmarkValues = dates.map((d) => {
    if (bmMap.has(d)) {
      lastBm = bmMap.get(d)!;
    }
    return lastBm;
  });


  return {
    legend: {
      data: ['Portfolio NAV', 'Benchmark (NIFTY 50)'],
      top: 0,
      textStyle: { fontSize: 11, color: '#64748b' },
    },
    tooltip: {
      trigger: 'axis',
      formatter: (params: Array<{ axisValue: string; data: number }>) => {
        const pt = params[0];
        const bm = params[1];
        return `<div class="p-1 font-sans text-xs">
          <div class="text-gray-500">${pt.axisValue}</div>
          <div class="font-bold text-gray-900 mt-1">NAV: ${pt.data}</div>
          ${bm ? `<div class="text-gray-600">Benchmark: ${bm.data}</div>` : ''}
        </div>`;
      },
    },
    grid: { left: '3%', right: '3%', bottom: '8%', top: '15%', containLabel: true },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: '#cbd5e1' } },
      axisLabel: { color: '#64748b', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLine: { show: false },
      splitLine: { lineStyle: { color: '#f1f5f9' } },
      axisLabel: { color: '#64748b', fontSize: 11 },
    },
    series: [
      {
        name: 'Portfolio NAV',
        type: 'line',
        data: navValues,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#0f172a', width: 2.5 },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(15, 23, 42, 0.12)' },
              { offset: 1, color: 'rgba(15, 23, 42, 0.0)' },
            ],
          },
        },
      },
      {
        name: 'Benchmark (NIFTY 50)',
        type: 'line',
        data: benchmarkValues,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#94a3b8', width: 1.5, type: 'dashed' },
      },
    ],
  };
}
