import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { formatPercent } from '@/lib/api';
import { fetchOrbHealth } from './api';
import { OrbCard } from './OrbCard';
import { QueryState } from './QueryState';

const STALE_SYNC_MS = 15 * 60 * 1000;

function syncLabel(at: string | null): { text: string; stale: boolean } {
  if (!at) return { text: 'never synced', stale: true };
  const age = Date.now() - new Date(at).getTime();
  return { text: `synced ${new Date(at).toLocaleString('en-IN')}`, stale: age > STALE_SYNC_MS };
}

export const HealthPanel: React.FC = () => {
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['orb', 'health'], queryFn: fetchOrbHealth });
  const sync = syncLabel(data?.last_synced_at ?? null);
  const test = data?.exit_test;

  return (
    <OrbCard
      title="Feed health"
      aside={data && <span className={sync.stale ? 'text-negative font-semibold' : ''}>{sync.stale ? 'Stale: ' : ''}{sync.text}</span>}
    >
      <QueryState
        isLoading={isLoading}
        error={error}
        isEmpty={!!data && data.sessions.length === 0 && !data.heartbeat}
        emptyText="No health records synced yet."
        onRetry={() => refetch()}
      >
        {data && test && (
          <div className="space-y-3 text-sm">
            <p className="text-ink">
              Exit test: <strong>{test.passed ? 'PASSED' : 'NOT PASSED'}</strong> ({test.sessions_passing}/{test.sessions_required} sessions
              at ≥ 99.5 % agreement; worst {formatPercent(test.worst_agree_ratio, 2).replace('+', '')})
            </p>
            {data.heartbeat && (
              <p className="text-subtle">
                Last v1 engine heartbeat: {data.heartbeat.trade_date} {data.heartbeat.time ?? ''}{' '}
                ({data.heartbeat.market_open ? 'market open' : 'market closed'})
              </p>
            )}
            <table className="w-full text-xs" aria-label="Reconciliation sessions">
              <thead className="text-subtle text-left">
                <tr><th className="py-1">Date</th><th>Agreement</th><th>Symbols</th><th>Exit-test day</th></tr>
              </thead>
              <tbody>
                {data.sessions.map((s) => (
                  <tr key={s.trade_date ?? ''} className="border-t border-hairline">
                    <td className="py-1">{s.trade_date}</td>
                    <td>{formatPercent(s.agree_ratio, 2).replace('+', '')}</td>
                    <td>{s.symbols ?? '—'}</td>
                    <td>{s.passes_exit_test == null ? '—' : s.passes_exit_test ? 'yes' : 'no'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </QueryState>
    </OrbCard>
  );
};
