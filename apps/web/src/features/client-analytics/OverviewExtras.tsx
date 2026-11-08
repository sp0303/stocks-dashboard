import React from 'react';
import { AnalyticsGate } from './AnalyticsGate';
import { HealthCard } from './HealthCard';
import { HighlightsCard } from './HighlightsCard';
import { ManualTradesCard } from './ManualTradesCard';
import { SensitivityStats } from './SensitivityStats';
import { useAnalyticsSummary } from './useAnalytics';

/** Overview additions: beta/alpha, intraday pool, health score, highlights, manual trades. */
const OverviewExtras: React.FC<{ clientId: string }> = ({ clientId }) => {
  const q = useAnalyticsSummary(clientId);
  const s = q.data?.data;
  return (
    <AnalyticsGate isLoading={q.isLoading} error={q.error} onRetry={() => q.refetch()}>
      {s && (
        <div className="space-y-4">
          <SensitivityStats s={s} />
          <div className="grid lg:grid-cols-2 gap-4">
            <HealthCard health={s.health} />
            <HighlightsCard items={s.highlights} />
          </div>
          <ManualTradesCard rows={s.manual_trades} />
        </div>
      )}
    </AnalyticsGate>
  );
};

export default OverviewExtras;
