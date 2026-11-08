import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { formatPercent } from '@/lib/api';
import { fetchOrbJournal } from './api';
import { OrbCard } from './OrbCard';
import { QueryState } from './QueryState';

const fmtR = (v: number | null) => (v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(2)} R`);

export const JournalPanel: React.FC = () => {
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['orb', 'journal'], queryFn: fetchOrbJournal });

  return (
    <OrbCard title="Paper journal (30 days)" aside={data ? `Since ${data.since}` : undefined}>
      <QueryState
        isLoading={isLoading}
        error={error}
        isEmpty={!!data && data.count === 0}
        emptyText="No closed paper trades in the last 30 days."
        onRetry={() => refetch()}
      >
        {data && (
          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <div><dt className="text-subtle text-xs">Trades</dt><dd className="font-bold text-ink">{data.count}</dd></div>
            <div>
              <dt className="text-subtle text-xs">Total</dt>
              <dd className={`font-bold ${data.total_r < 0 ? 'text-negative' : 'text-ink'}`}>{fmtR(data.total_r)}</dd>
            </div>
            <div><dt className="text-subtle text-xs">Win rate</dt><dd className="font-bold text-ink">{formatPercent(data.win_rate, 1).replace('+', '')}</dd></div>
            <div><dt className="text-subtle text-xs">Expectancy</dt><dd className="font-bold text-ink">{fmtR(data.expectancy_r)}</dd></div>
          </dl>
        )}
      </QueryState>
    </OrbCard>
  );
};
