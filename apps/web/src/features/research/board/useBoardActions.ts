import { useQueryClient } from '@tanstack/react-query';
import {
  createBoardItem,
  deleteBoardItem,
  updateBoardItem,
  type BoardItemResponse,
  type BoardItemUpdate,
  type ManagerHoldingsItem,
  type WatchlistEntryItem,
} from '@/lib/api';

/** Board writes; every one refreshes the board query. Errors are surfaced via `onError`. */
export function useBoardActions(ownerId: string, onError: (msg: string) => void) {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ['board', ownerId] });
  const run = async (fn: () => Promise<unknown>, what: string) => {
    try {
      await fn();
      await refresh();
    } catch (e) {
      onError(`Could not ${what}: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  return {
    update: (itemId: string, patch: BoardItemUpdate) => run(() => updateBoardItem(itemId, patch), 'update the card'),
    remove: (itemId: string) => run(() => deleteBoardItem(itemId), 'remove the card'),

    /** Holding notes live on a holding-lane card for that symbol (created on first save). */
    saveHoldingNotes: (symbol: string, why: string, existing?: BoardItemResponse) =>
      run(
        () =>
          existing
            ? updateBoardItem(existing.item_id, { why })
            : createBoardItem({ owner_id: ownerId, symbol, lane: 'holding', why }),
        'save notes',
      ),

    planExitFromHolding: (h: ManagerHoldingsItem) =>
      run(
        () => createBoardItem({ owner_id: ownerId, symbol: h.symbol, lane: 'exit', entry_price: h.avg_cost }),
        'plan the exit',
      ),

    planExitFromWatchlist: (e: WatchlistEntryItem) =>
      run(
        () =>
          createBoardItem({
            owner_id: ownerId,
            symbol: e.symbol,
            lane: 'exit',
            entry_price: e.added_price ?? null,
            why: e.why ?? null,
          }),
        'plan the exit',
      ),
  };
}
