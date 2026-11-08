import React, { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { LineChart, BarChart } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([
  LineChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  CanvasRenderer,
]);

interface EChartProps {
  options: echarts.EChartsCoreOption;
  height?: string | number;
  className?: string;
  theme?: 'light' | 'dark';
}

export const EChart: React.FC<EChartProps> = ({
  options,
  height = 350,
  className = '',
  theme = 'light',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    if (!chartInstance.current) {
      chartInstance.current = echarts.init(containerRef.current, theme);
    }

    chartInstance.current.setOption(options, true);

    const handleResize = () => {
      chartInstance.current?.resize();
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, [options, theme]);

  useEffect(() => {
    return () => {
      chartInstance.current?.dispose();
      chartInstance.current = null;
    };
  }, []);

  return (
    <div
      ref={containerRef}
      style={{ height, width: '100%' }}
      className={`rounded-card overflow-hidden ${className}`}
    />
  );
};
