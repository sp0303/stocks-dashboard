import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchOrbSignals } from './api';
import { OrbCard } from './OrbCard';
import { QueryState } from './QueryState';
import { EntriesTable } from './EntriesTable';
import { CandidatesTable } from './CandidatesTable';

export const SignalsPanel: React.FC<{ date: string | null }> = ({ date }) => {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['orb', 'signals', date],
    queryFn: () => fetchOrbSignals(date),
  });
  const screen = data?.screen ?? null;

  return (
    <OrbCard title="Screen & signals" aside={data?.trade_date ? `Session ${data.trade_date}` : undefined}>
      <QueryState
        isLoading={isLoading}
        error={error}
        isEmpty={!!data && !screen && data.entries.length === 0}
        emptyText="No ORB screen or signals for this session."
        onRetry={() => refetch()}
      >
        <div className="space-y-4">
          {screen && (
            <div className="space-y-1">
              <p className="text-sm text-ink">
                {screen.passed ?? 0} of {screen.candidates ?? 0} candidates passed. Shortlist:{' '}
                <strong>{screen.shortlist.length ? screen.shortlist.join(', ') : 'none'}</strong>
              </p>
              {screen.config && <p className="text-xs text-subtle">Config {screen.config}</p>}
            </div>
          )}
          <EntriesTable entries={data?.entries ?? []} />
          {screen && screen.rows.length > 0 && <CandidatesTable rows={screen.rows} />}
        </div>
      </QueryState>
    </OrbCard>
  );
};
