import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { Radar } from 'lucide-react';
import { HealthPanel } from './HealthPanel';
import { SignalsPanel } from './SignalsPanel';
import { UniversePanel } from './UniversePanel';
import { JournalPanel } from './JournalPanel';

/** ORB page: composition only. The session date lives in the URL (?date=YYYY-MM-DD). */
export const OrbPage: React.FC = () => {
  const [params, setParams] = useSearchParams();
  const date = params.get('date');

  const onDate = (value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set('date', value);
    else next.delete('date');
    setParams(next, { replace: true });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Radar className="w-5 h-5 text-positive" aria-hidden="true" />
          <h1 className="text-xl font-bold text-ink">Opening Range Breakout</h1>
        </div>
        <label className="text-sm text-subtle flex items-center gap-2">
          Session
          <input
            type="date"
            value={date ?? ''}
            onChange={(e) => onDate(e.target.value)}
            className="px-3 py-1.5 rounded-interactive border border-hairline bg-paper text-ink text-sm"
          />
        </label>
      </div>
      <p className="text-xs text-subtle">
        Read-only mirror of the v1 ORB engine (paper only), synced from v1 every few minutes. Latest session shown when no date is picked.
      </p>
      <HealthPanel />
      <SignalsPanel date={date} />
      <div className="grid gap-6 lg:grid-cols-2">
        <UniversePanel date={date} />
        <JournalPanel />
      </div>
    </div>
  );
};
