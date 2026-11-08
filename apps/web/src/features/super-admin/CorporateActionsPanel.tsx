import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CalendarClock, RefreshCw } from 'lucide-react';
import { fetchCorporateActionsStatus, requestCorporateActionsRefresh } from '@/lib/apiAdmin';
import { ErrorBlock, LoadingBlock } from '@/components/QueryStates';
import { ConfirmDialog } from './ConfirmDialog';

const KEY = ['admin', 'corporate-actions'];
const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString('en-IN') : '—');

/** "N actions stored · M symbols" + queue a held-symbol refresh or a full NSE backfill (worker does the fetch). */
export const CorporateActionsPanel: React.FC = () => {
  const qc = useQueryClient();
  const [confirmAll, setConfirmAll] = useState(false);
  const q = useQuery({
    queryKey: KEY,
    queryFn: fetchCorporateActionsStatus,
    refetchInterval: (query) => (query.state.data?.last_run?.status === 'RUNNING' ? 10_000 : false),
  });
  const refresh = useMutation({
    mutationFn: requestCorporateActionsRefresh,
    onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: KEY }), 3000),
  });

  const run = q.data?.last_run;
  return (
    <section className="bg-paper border border-hairline rounded-card p-5 shadow-sm space-y-3" aria-labelledby="ca-title">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 id="ca-title" className="text-base font-semibold text-ink flex items-center gap-2">
          <CalendarClock className="w-5 h-5 text-subtle" aria-hidden /> Corporate-actions data
        </h2>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={refresh.isPending}
            onClick={() => refresh.mutate('held')}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-interactive bg-ink text-paper text-xs font-semibold disabled:opacity-40"
          >
            <RefreshCw className="w-3.5 h-3.5" aria-hidden /> Refresh held symbols
          </button>
          <button
            type="button"
            disabled={refresh.isPending}
            onClick={() => setConfirmAll(true)}
            className="px-3 py-1.5 rounded-interactive border border-hairline text-xs font-semibold text-ink hover:bg-canvas disabled:opacity-40"
          >
            Backfill all NSE
          </button>
        </div>
      </div>
      {q.isLoading && <LoadingBlock rows={1} label="Loading corporate-actions status" />}
      {q.isError && <ErrorBlock message="Could not load corporate-actions status." onRetry={() => q.refetch()} />}
      {q.data && (
        <div className="text-sm text-ink">
          <span className="font-semibold">{q.data.actions.toLocaleString('en-IN')}</span> actions stored ·{' '}
          <span className="font-semibold">{q.data.symbols.toLocaleString('en-IN')}</span> symbols
          <div className="text-xs text-subtle mt-1">
            Last fetched {when(q.data.last_fetched_at)}
            {run ? ` · last run ${run.status} (${when(run.started_at)})${run.error ? ` — ${run.error}` : ''}` : ' · never refreshed in v2'}
          </div>
          {q.data.actions === 0 && <div className="text-xs text-subtle mt-1">No actions stored yet — run “Refresh held symbols”.</div>}
        </div>
      )}
      {refresh.isSuccess && (
        <p className="text-xs text-positive" role="status">
          Queued ({refresh.data.scope}). The worker fetches from NSE at a polite pace; a full backfill takes a while.
        </p>
      )}
      {refresh.isError && <p role="alert" className="text-xs text-negative">{(refresh.error as Error).message}</p>}
      {confirmAll && (
        <ConfirmDialog
          title="Backfill every NSE symbol?"
          message="This queues a fetch for every listed NSE equity (about 2,000 symbols, roughly 30 minutes at the polite rate)."
          confirmLabel="Queue backfill"
          onConfirm={() => refresh.mutateAsync('all')}
          onClose={() => setConfirmAll(false)}
        />
      )}
    </section>
  );
};
