import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchOrbUniverse } from './api';
import { OrbCard } from './OrbCard';
import { QueryState } from './QueryState';

export const UniversePanel: React.FC<{ date: string | null }> = ({ date }) => {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['orb', 'universe', date],
    queryFn: () => fetchOrbUniverse(date),
  });

  return (
    <OrbCard title="Universe" aside={data?.trade_date ? `As of ${data.trade_date}` : undefined}>
      <QueryState
        isLoading={isLoading}
        error={error}
        isEmpty={!!data && !data.trade_date}
        emptyText="No ORB universe on or before this session."
        onRetry={() => refetch()}
      >
        {data && (
          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <div><dt className="text-subtle text-xs">Members</dt><dd className="font-bold text-ink">{data.size ?? data.members.length}</dd></div>
            <div><dt className="text-subtle text-xs">Sector-mapped</dt><dd className="font-bold text-ink">{data.sector_mapped}</dd></div>
            <div>
              <dt className="text-subtle text-xs">Min turnover</dt>
              <dd className="font-bold text-ink">{data.min_turnover_cr != null ? `₹ ${data.min_turnover_cr} cr` : '—'}</dd>
            </div>
            <div><dt className="text-subtle text-xs">Pool</dt><dd className="font-bold text-ink">{typeof data.pool === 'number' ? data.pool : '—'}</dd></div>
          </dl>
        )}
      </QueryState>
    </OrbCard>
  );
};
