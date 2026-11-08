import React from 'react';
import { HeartPulse } from 'lucide-react';
import type { Health } from '@/lib/apiAnalytics';
import { Card } from './Card';

/** 0–100 score; alerts are text (colour is never the only signal). */
export const HealthCard: React.FC<{ health: Health | null }> = ({ health }) => (
  <Card title="Portfolio health" icon={<HeartPulse className="w-5 h-5 text-subtle" aria-hidden />}>
    {health == null ? (
      <p className="text-xs text-subtle">No open holdings to score.</p>
    ) : (
      <div className="flex items-start gap-4">
        <div className="text-3xl font-bold text-ink" aria-label={`Health score ${health.score} of 100`}>
          {health.score}<span className="text-sm text-subtle">/100</span>
        </div>
        <ul className="text-xs space-y-1 flex-1">
          {health.alerts.length === 0 && <li className="text-subtle">No alerts.</li>}
          {health.alerts.map((a) => <li key={a.code} className="text-negative">⚠ {a.message}</li>)}
          {health.missing.length > 0 && <li className="text-subtle">Not scored (no data): {health.missing.join(', ')}</li>}
        </ul>
      </div>
    )}
  </Card>
);
