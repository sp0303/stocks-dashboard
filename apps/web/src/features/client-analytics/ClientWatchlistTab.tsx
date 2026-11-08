import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Eye } from 'lucide-react';
import { fetchWatchlists, formatRupees, type WatchlistResponse } from '@/lib/api';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryStates';
import { Card } from './Card';

/** The client's own watchlists (owner = client), read through the existing research endpoint. */
const ClientWatchlistTab: React.FC<{ clientId: string }> = ({ clientId }) => {
  const q = useQuery<WatchlistResponse[]>({ queryKey: ['watchlists', clientId], queryFn: () => fetchWatchlists(clientId) });
  const lists = q.data ?? [];
  let body: React.ReactNode;
  if (q.isLoading) body = <LoadingBlock rows={3} label="Loading watchlists" />;
  else if (q.error) body = <ErrorBlock message="Failed to load watchlists" onRetry={() => q.refetch()} />;
  else if (lists.every((l) => l.entries.length === 0)) body = <EmptyBlock title="No watchlist entries for this client" />;
  else {
    body = lists.filter((l) => l.entries.length > 0).map((l) => (
      <div key={l.watchlist_id} className="mb-4">
        <h3 className="text-sm font-semibold text-ink mb-2">{l.name}{l.is_default ? ' (default)' : ''}</h3>
        <table className="w-full text-sm" aria-label={`Watchlist ${l.name}`}>
          <thead className="text-[11px] uppercase text-subtle">
            <tr>{['Stock', 'Added', 'Added at', 'Alert', 'Why'].map((c) => <th key={c} scope="col" className="text-left py-2 pr-3">{c}</th>)}</tr>
          </thead>
          <tbody>
            {l.entries.map((e) => (
              <tr key={e.symbol} className="border-t border-hairline">
                <td className="py-1.5 pr-3 font-semibold text-ink">{e.symbol}</td>
                <td className="py-1.5 pr-3 text-subtle">{e.added_date}</td>
                <td className="py-1.5 pr-3 font-mono text-ink">{formatRupees(e.added_price)}</td>
                <td className="py-1.5 pr-3 font-mono text-ink">{formatRupees(e.alert_price)}</td>
                <td className="py-1.5 text-subtle">{e.why || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ));
  }
  return <Card title="Watchlist" icon={<Eye className="w-5 h-5 text-subtle" aria-hidden />}>{body}</Card>;
};

export default ClientWatchlistTab;
