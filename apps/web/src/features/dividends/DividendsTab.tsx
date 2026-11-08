import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Coins, Plus, SearchCheck } from 'lucide-react';
import { formatRupees } from '@/lib/api';
import { deleteDividend, fetchDividends, type DividendItem } from '@/lib/apiLedger';
import { useAuthStore } from '@/stores/authStore';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryStates';
import { AddDividendForm } from './AddDividendForm';
import { DividendsTable } from './DividendsTable';
import { DividendSuggestions } from './DividendSuggestions';

interface Props {
  clientId: string;
}

export const DividendsTab: React.FC<Props> = ({ clientId }) => {
  const role = useAuthStore((s) => s.role);
  const canEdit = role !== 'client';
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [finding, setFinding] = useState(false);

  const { data, isLoading, error, refetch } = useQuery<DividendItem[]>({
    queryKey: ['dividends', clientId],
    queryFn: () => fetchDividends(clientId),
  });

  const remove = useMutation({
    mutationFn: (id: number) => deleteDividend(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dividends', clientId] }),
  });

  const total = (data ?? []).reduce((acc, d) => acc + d.amount, 0);

  const onDelete = (d: DividendItem) => {
    if (window.confirm(`Delete the ${d.symbol} dividend of ${formatRupees(d.amount)} (ex ${d.ex_date})?`)) {
      remove.mutate(d.dividend_id);
    }
  };

  return (
    <section className="bg-paper border border-hairline rounded-card overflow-hidden shadow-sm" aria-label="Dividends">
      <div className="p-5 border-b border-hairline flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Coins className="w-5 h-5 text-subtle" aria-hidden />
          <h2 className="text-base font-semibold text-ink">Dividends</h2>
          {data && data.length > 0 && (
            <span className="text-xs text-subtle">
              {data.length} · total <strong className="text-ink">{formatRupees(total)}</strong>
            </span>
          )}
        </div>
        {canEdit && (
          <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setFinding((v) => !v)}
            aria-expanded={finding}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-interactive border border-hairline bg-paper text-xs font-semibold text-ink hover:bg-canvas"
          >
            <SearchCheck className="w-3.5 h-3.5" aria-hidden /> {finding ? 'Hide suggestions' : 'Find missing dividends'}
          </button>
          <button
            type="button"
            onClick={() => setAdding((v) => !v)}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-interactive border border-hairline bg-paper text-xs font-semibold text-ink hover:bg-canvas"
          >
            <Plus className="w-3.5 h-3.5" aria-hidden /> {adding ? 'Close' : 'Add dividend'}
          </button>
          </div>
        )}
      </div>

      {finding && canEdit && <DividendSuggestions clientId={clientId} />}
      {adding && canEdit && <AddDividendForm clientId={clientId} onDone={() => setAdding(false)} />}
      {remove.error && <ErrorBlock message={(remove.error as Error).message} />}

      {isLoading && <LoadingBlock rows={3} label="Loading dividends" />}
      {!isLoading && error && <ErrorBlock message={(error as Error).message} onRetry={() => refetch()} />}
      {!isLoading && !error && data && data.length === 0 && (
        <EmptyBlock
          icon={<Coins className="w-6 h-6" aria-hidden />}
          title="No dividends recorded yet"
          hint={canEdit ? 'Use “Add dividend” to record one manually.' : undefined}
        />
      )}
      {!isLoading && !error && data && data.length > 0 && (
        <DividendsTable rows={data} canEdit={canEdit} busy={remove.isPending} onDelete={onDelete} />
      )}
    </section>
  );
};

export default DividendsTab;
