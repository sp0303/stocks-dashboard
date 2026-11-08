import React from 'react';

interface MetricCardProps {
  title: string;
  value: string;
  subValue?: string;
  badge?: string;
  trend?: 'positive' | 'negative' | 'neutral';
  tooltip?: string;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  subValue,
  badge,
  trend = 'neutral',
  tooltip,
}) => {
  const trendClass =
    trend === 'positive'
      ? 'text-positive font-medium'
      : trend === 'negative'
      ? 'text-negative font-medium'
      : 'text-subtle';

  return (
    <div className="bg-paper border border-hairline rounded-card p-5 shadow-sm transition-all hover:shadow-md">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-subtle uppercase tracking-wider" title={tooltip}>
          {title}
        </span>
        {badge && (
          <span className="text-[11px] px-2 py-0.5 rounded-full bg-canvas text-subtle font-medium border border-hairline">
            {badge}
          </span>
        )}
      </div>
      <div className="mt-2 text-2xl font-bold tracking-tight text-ink">
        {value}
      </div>
      {subValue && (
        <div className={`mt-1 text-xs ${trendClass}`}>
          {subValue}
        </div>
      )}
    </div>
  );
};
