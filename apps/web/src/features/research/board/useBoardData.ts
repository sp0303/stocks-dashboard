import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  fetchBoard,
  fetchManagerHoldings,
  fetchWatchlists,
  type BoardItemResponse,
  type ManagerHoldingsItem,
  type WatchlistResponse,
} from '@/lib/api';
import { fetchCloses } from '@/lib/apiResearch';
import { priceMap, symbolKey } from './boardMath';

/**
 * Everything the board shows, fetched in parallel (as v1's MyBoard did):
 * manual cards, the manager's real holdings, their watchlists, and the latest close
 * for every symbol on a manual or watchlist card.
 */
export function useBoardData(ownerId: string) {
  const board = useQuery<BoardItemResponse[]>({
    queryKey: ['board', ownerId],
    queryFn: () => fetchBoard(ownerId),
  });
  const holdings = useQuery<ManagerHoldingsItem[]>({
    queryKey: ['managerHoldings', ownerId],
    queryFn: () => fetchManagerHoldings(ownerId),
  });
  const watchlists = useQuery<WatchlistResponse[]>({
    queryKey: ['watchlists', ownerId],
    queryFn: () => fetchWatchlists(ownerId),
  });

  const symbols = useMemo(() => {
    const s = new Set<string>();
    for (const b of board.data ?? []) s.add(symbolKey(b.symbol));
    for (const w of watchlists.data ?? []) for (const e of w.entries) s.add(symbolKey(e.symbol));
    return [...s].sort();
  }, [board.data, watchlists.data]);

  const closes = useQuery({
    queryKey: ['latestCloses', symbols.join(',')],
    queryFn: () => fetchCloses(symbols),
    enabled: symbols.length > 0,
  });
  const prices = useMemo(() => priceMap(closes.data), [closes.data]);

  return { board, holdings, watchlists, prices };
}
