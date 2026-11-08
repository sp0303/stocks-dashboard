import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { WatchlistResponse } from '@/lib/api';
import { fetchCloses } from '@/lib/apiResearch';
import { ErrorBlock } from '@/components/QueryStates';
import { priceMap, symbolKey } from './board/boardMath';
import { WatchlistRow } from './WatchlistRow';

interface Props {
  watchlist: WatchlistResponse;
  onDelete: (symbol: string) => void;
}

const HEAD: Array<[string, boolean]> = [
  ['Symbol', false], ['Sector', false], ['Last close', true], ['Entry', true], ['vs entry', true],
  ['Alert', true], ['Thesis / Catalyst', false], ['Action', true],
];

/** Watchlist entries with the latest stored close (R6: as_of shown, stale flagged, unpriced as text). */
export const WatchlistTable: React.FC<Props> = ({ watchlist, onDelete }) => {
  const symbols = useMemo(
    () => [...new Set(watchlist.entries.map((e) => symbolKey(e.symbol)))].sort(),
    [watchlist.entries],
  );
  const closes = useQuery({
    queryKey: ['latestCloses', symbols.join(',')],
    queryFn: () => fetchCloses(symbols),
    enabled: symbols.length > 0,
  });
  const prices = useMemo(() => priceMap(closes.data), [closes.data]);

  return (
    <div className="bg-paper border border-hairline rounded-card overflow-hidden shadow-sm">
      {closes.error && <ErrorBlock message={(closes.error as Error).message} onRetry={() => closes.refetch()} />}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-sm" aria-label={`Watchlist ${watchlist.name}`} aria-busy={closes.isLoading}>
          <thead>
            <tr className="bg-canvas/60 text-subtle text-xs border-b border-hairline">
              {HEAD.map(([h, right]) => (
                <th key={h} className={`py-3 px-4 font-semibold ${right ? 'text-right' : ''}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {watchlist.entries.map((entry) => (
              <WatchlistRow key={entry.symbol} entry={entry} quote={prices.get(symbolKey(entry.symbol))} onDelete={onDelete} />
            ))}
            {watchlist.entries.length === 0 && (
              <tr>
                <td colSpan={HEAD.length} className="py-12 text-center text-subtle text-sm">
                  No symbols in this watchlist yet. Click "+ Add Symbol" to track a ticker.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
