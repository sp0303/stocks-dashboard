import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { NotebookPen } from 'lucide-react';
import { fetchThesis, saveThesis, type StockThesis } from '@/lib/apiResearch';
import { ErrorBlock, LoadingBlock } from '@/components/QueryStates';
import { ThesisEditor } from './ThesisEditor';

interface Props {
  clientId: string;
  symbol: string;
  canEdit: boolean;
}

function text(v: unknown): string {
  if (v == null) return '';
  return typeof v === 'string' ? v : JSON.stringify(v);
}

/** Thesis from research.stock_theses. Unknown keys are shown read-only and preserved on save. */
export const ThesisPanel: React.FC<Props> = ({ clientId, symbol, canEdit }) => {
  const qc = useQueryClient();
  const key = ['thesis', clientId, symbol];
  const [editing, setEditing] = useState(false);
  const { data, isLoading, error, refetch } = useQuery<StockThesis | null>({
    queryKey: key,
    queryFn: () => fetchThesis(clientId, symbol),
  });

  const save = useMutation({
    mutationFn: (patch: Record<string, string>) => saveThesis(clientId, symbol, { ...(data?.thesis ?? {}), ...patch }),
    onSuccess: (res) => {
      qc.setQueryData(key, res);
      setEditing(false);
    },
  });

  if (isLoading) return <LoadingBlock rows={2} label="Loading thesis" />;
  if (error) return <ErrorBlock message={(error as Error).message} onRetry={() => refetch()} />;

  const thesis = data?.thesis ?? {};
  const entries = Object.entries(thesis).filter(([, v]) => text(v).trim() !== '');

  if (editing) {
    return (
      <ThesisEditor
        initial={{ remarks: text(thesis.remarks), risks: text(thesis.risks) }}
        saving={save.isPending}
        error={save.error ? (save.error as Error).message : null}
        onCancel={() => setEditing(false)}
        onSave={(patch) => save.mutate(patch)}
      />
    );
  }

  return (
    <div className="space-y-3">
      {entries.length === 0 ? (
        <div className="text-xs text-subtle py-4 text-center flex flex-col items-center gap-2">
          <NotebookPen className="w-5 h-5" aria-hidden />
          No thesis recorded for {symbol}.
        </div>
      ) : (
        <dl className="space-y-2">
          {entries.map(([k, v]) => (
            <div key={k}>
              <dt className="text-[11px] font-semibold uppercase text-subtle">{k.replace(/_/g, ' ')}</dt>
              <dd className="text-sm text-ink whitespace-pre-wrap">{text(v)}</dd>
            </div>
          ))}
        </dl>
      )}
      {data?.updated_at && <div className="text-[11px] text-subtle">Updated {data.updated_at.slice(0, 10)}</div>}
      {canEdit && (
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="px-3 py-1.5 rounded-interactive border border-hairline bg-paper text-xs font-semibold text-ink hover:bg-canvas"
        >
          {entries.length ? 'Edit thesis' : 'Write thesis'}
        </button>
      )}
    </div>
  );
};
