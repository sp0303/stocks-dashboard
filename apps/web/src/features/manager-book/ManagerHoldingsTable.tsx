import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchManagerHoldings, formatPercent, formatRupees } from '@/lib/api';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryStates';
import { aggregateHoldings } from './holdingsAggregate';
import { ClientMultiSelect } from './ClientMultiSelect';
import { HoldingRow } from './HoldingRow';
import { useBookSummary, useUrlParam } from './useBook';

const HEAD = ['Symbol', 'Clients', 'Qty', 'Invested', 'Price', 'Market value', 'Unrealised', 'Return'];

/** Holdings by selected clients: the selection (URL param `hc`) re-aggregates rows and totals. */
export const ManagerHoldingsTable: React.FC<{ managerId: string }> = ({ managerId }) => {
  const q = useQuery({ queryKey: ['manager', managerId, 'holdings'], queryFn: () => fetchManagerHoldings(managerId) });
  const roster = useBookSummary(managerId);
  const [hc, setHc] = useUrlParam('hc');
  const selected = useMemo(() => new Set(hc ? hc.split(',') : []), [hc]);
  const agg = useMemo(() => (q.data ? aggregateHoldings(q.data, selected) : null), [q.data, selected]);

  if (q.isLoading) return <LoadingBlock rows={6} label="Loading holdings" />;
  if (q.isError || !agg) return <ErrorBlock message="Could not load the book's holdings." onRetry={() => q.refetch()} />;
  const t = agg.totals;
  return (
    <div className="bg-paper border border-hairline rounded-card overflow-hidden shadow-sm">
      <div className="p-5 border-b border-hairline space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-base font-semibold text-ink">Holdings by selected clients</h2>
          <span className="text-xs text-subtle">
            {agg.rows.length} symbols · invested {formatRupees(t.invested, 0)} · value {formatRupees(t.marketValue, 0)} ·{' '}
            <span className={t.unrealized < 0 ? 'text-negative' : 'text-positive'}>{formatRupees(t.unrealized, 0)} ({formatPercent(t.returnPct)})</span>
            {t.unpriced > 0 && ` · ${t.unpriced} unpriced, excluded`}
          </span>
        </div>
        <ClientMultiSelect clients={roster.data?.clients ?? []} selected={selected} onChange={(s) => setHc([...s].join(','))} />
      </div>
      {agg.rows.length === 0 ? (
        <EmptyBlock title="No open holdings" hint={selected.size ? 'The selected clients hold nothing.' : 'No client holds a position.'} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm" aria-label="Aggregated holdings">
            <thead>
              <tr className="bg-canvas/60 text-subtle text-xs border-b border-hairline">
                {HEAD.map((h, i) => (
                  <th key={h} className={`py-3 px-4 font-semibold ${i ? 'text-right' : ''}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {agg.rows.map((h) => (
                <HoldingRow key={`${h.symbol}:${h.exchange}`} h={h} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
