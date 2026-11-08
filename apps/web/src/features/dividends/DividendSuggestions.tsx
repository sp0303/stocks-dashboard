import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { SearchCheck } from 'lucide-react';
import { createDividend, fetchDividendSuggestions, type DividendSuggestion } from '@/lib/apiLedger';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryStates';
import { SuggestionRow } from './SuggestionRow';

interface Props {
  clientId: string;
}

const th = 'py-2 px-3 font-semibold';

/** v1's "Find missing dividends": proposals from stored corporate actions; a row is recorded only on Accept. */
export const DividendSuggestions: React.FC<Props> = ({ clientId }) => {
  const qc = useQueryClient();
  const q = useQuery<DividendSuggestion[]>({
    queryKey: ['dividendSuggestions', clientId],
    queryFn: () => fetchDividendSuggestions(clientId),
  });
  const accept = useMutation({
    mutationFn: (s: DividendSuggestion) =>
      createDividend({
        client_id: clientId,
        symbol: s.symbol,
        ex_date: s.ex_date,
        amount_per_share: s.amount_per_share,
        quantity: s.estimated_quantity,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dividends', clientId] });
      qc.invalidateQueries({ queryKey: ['dividendSuggestions', clientId] });
    },
  });

  return (
    <div className="border-b border-hairline" aria-label="Missing dividend suggestions">
      <div className="px-5 pt-4 text-xs text-subtle">
        Proposed from stored corporate actions for the quantity held before each ex-date. Check against the
        bank credit before accepting; nothing is recorded until you accept.
      </div>
      {accept.error && <ErrorBlock message={(accept.error as Error).message} />}
      {q.isLoading && <LoadingBlock rows={2} label="Finding missing dividends" />}
      {!q.isLoading && q.error && <ErrorBlock message={(q.error as Error).message} onRetry={() => q.refetch()} />}
      {!q.isLoading && !q.error && (q.data?.length ?? 0) === 0 && (
        <EmptyBlock icon={<SearchCheck className="w-6 h-6" aria-hidden />} title="No missing dividends found" />
      )}
      {!q.isLoading && !q.error && (q.data?.length ?? 0) > 0 && (
        <div className="overflow-x-auto p-3">
          <table className="w-full text-left text-xs" aria-label="Suggested dividends">
            <thead>
              <tr className="text-subtle border-b border-hairline">
                <th className={th}>Symbol</th><th className={th}>Ex-date</th>
                <th className={`${th} text-right`}>Per share</th><th className={`${th} text-right`}>Held qty</th>
                <th className={`${th} text-right`}>Est. amount</th><th className={`${th} text-right`}>Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {q.data!.map((s) => (
                <SuggestionRow key={`${s.symbol}-${s.ex_date}`} s={s} busy={accept.isPending} onAccept={accept.mutate} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
