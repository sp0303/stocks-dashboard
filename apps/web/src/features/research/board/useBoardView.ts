import { useMemo } from 'react';
import type { BoardItemResponse, ManagerHoldingsItem, WatchlistEntryItem, WatchlistResponse } from '@/lib/api';
import { clientsOf, holdingForClients } from './boardMath';

export interface WatchlistCardRow {
  key: string;
  entry: WatchlistEntryItem;
  listName: string;
}

/**
 * Splits the raw data into the three lanes, as v1's MyBoard did:
 *  - Holding  = real positions (re-totalled for the selected clients) + manual holding cards
 *  - Watching = manual watching cards + entries of the selected watchlists (deduped by symbol)
 *  - Exit     = manual exit plans
 */
export function useBoardView(
  board: BoardItemResponse[] | undefined,
  holdings: ManagerHoldingsItem[] | undefined,
  watchlists: WatchlistResponse[] | undefined,
  selectedClients: Set<string> | null,
  selectedLists: Set<string> | null,
) {
  return useMemo(() => {
    const items = board ?? [];
    const byLane = (lane: string) => items.filter((i) => i.lane === lane).sort((a, b) => a.sort_order - b.sort_order);

    const realHoldings = (holdings ?? [])
      .map((h) => holdingForClients(h, selectedClients))
      .filter((h): h is ManagerHoldingsItem => h !== null);
    const heldSymbols = new Set(realHoldings.map((h) => h.symbol.toUpperCase()));
    const holdingCards = byLane('holding');
    const holdingNotes = new Map(holdingCards.map((c) => [c.symbol.toUpperCase(), c]));
    const manualHolding = holdingCards.filter((c) => !heldSymbols.has(c.symbol.toUpperCase()));

    const watching = byLane('watching');
    const onBoard = new Set(watching.map((w) => w.symbol.toUpperCase()));
    const watchlistCards: WatchlistCardRow[] = [];
    for (const wl of watchlists ?? []) {
      if (selectedLists !== null && !selectedLists.has(wl.watchlist_id)) continue;
      for (const e of wl.entries) {
        const sym = e.symbol.toUpperCase();
        if (onBoard.has(sym)) continue;
        onBoard.add(sym);
        watchlistCards.push({ key: `${wl.watchlist_id}:${sym}`, entry: e, listName: wl.name });
      }
    }

    return {
      realHoldings,
      holdingNotes,
      manualHolding,
      watching,
      watchlistCards,
      exits: byLane('exit'),
      clientOptions: clientsOf(holdings),
      listOptions: (watchlists ?? []).map((w) => ({ id: w.watchlist_id, name: w.name })),
    };
  }, [board, holdings, watchlists, selectedClients, selectedLists]);
}
