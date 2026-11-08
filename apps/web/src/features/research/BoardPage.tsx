import React, { useState } from 'react';
import { Columns3, Plus } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '@/stores/authStore';
import { AddBoardCardModal } from './AddBoardCardModal';
import { BoardFilters } from './board/BoardFilters';
import { BoardLane } from './board/BoardLane';
import { HoldingCard } from './board/HoldingCard';
import { PlanCard } from './board/PlanCard';
import { WatchlistEntryCard } from './board/WatchlistEntryCard';
import { useBoardActions } from './board/useBoardActions';
import { useBoardData } from './board/useBoardData';
import { useBoardView } from './board/useBoardView';
import { symbolKey, type Lane } from './board/boardMath';

/** v1 MyBoard parity: real holdings, watchlist-fed Watching, exit plans — all priced at the latest close. */
export const BoardPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { managerId, impersonatedManagerId } = useAuthStore();
  // Match ManagerBook: a super-admin impersonating a manager must see that manager's board.
  const ownerId = impersonatedManagerId || managerId || '00000000-0000-0000-0000-000000000000';

  const [selectedClients, setSelectedClients] = useState<Set<string> | null>(null);
  const [selectedLists, setSelectedLists] = useState<Set<string> | null>(null);
  const [addLane, setAddLane] = useState<Lane | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const { board, holdings, watchlists, prices } = useBoardData(ownerId);
  const view = useBoardView(board.data, holdings.data, watchlists.data, selectedClients, selectedLists);
  const act = useBoardActions(ownerId, setActionError);

  if (board.isLoading) {
    return <div className="p-8 text-center text-subtle text-sm animate-pulse">Loading board…</div>;
  }
  if (board.error) {
    return (
      <div className="p-8 text-center text-ember text-sm bg-ember/10 rounded-2xl space-y-2">
        <p>Failed to load board cards.</p>
        <button onClick={() => board.refetch()} className="underline">Retry</button>
      </div>
    );
  }

  const holdingCount = view.realHoldings.length + view.manualHolding.length;
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Columns3 className="w-5 h-5 text-positive" />
          <h1 className="text-xl font-bold text-ink">Research Kanban Board</h1>
        </div>
        <button onClick={() => setAddLane('watching')} className="flex items-center gap-1.5 px-3.5 py-2 rounded-2xl bg-ink text-paper text-xs font-semibold">
          <Plus className="w-4 h-4" /> Add Card
        </button>
      </div>

      <div className="space-y-2">
        <BoardFilters label="Clients" options={view.clientOptions} selected={selectedClients} onChange={setSelectedClients} />
        <BoardFilters label="Watchlists" options={view.listOptions} selected={selectedLists} onChange={setSelectedLists} />
      </div>
      {actionError && (
        <div role="alert" className="text-xs text-ember bg-ember/10 rounded-xl px-3 py-2 flex justify-between">
          {actionError}
          <button onClick={() => setActionError(null)} aria-label="Dismiss">×</button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-start">
        <BoardLane title="Watching" count={view.watching.length + view.watchlistCards.length} badge="bg-slate-100 text-slate-700" onAdd={() => setAddLane('watching')}>
          {view.watching.map((i) => <PlanCard key={i.item_id} item={i} quote={prices.get(symbolKey(i.symbol))} onUpdate={act.update} onDelete={act.remove} />)}
          {view.watchlistCards.map((w) => <WatchlistEntryCard key={w.key} entry={w.entry} listName={w.listName} quote={prices.get(symbolKey(w.entry.symbol))} onPlanExit={act.planExitFromWatchlist} />)}
        </BoardLane>

        <BoardLane
          title="Holding"
          count={holdingCount}
          badge="bg-positive/10 text-positive"
          hint={holdings.error ? 'Could not load real holdings.' : holdings.isLoading ? 'Loading real holdings…' : 'Real positions across selected clients, latest close.'}
          onAdd={() => setAddLane('holding')}
        >
          {view.realHoldings.map((h) => (
            <HoldingCard
              key={h.security_id}
              holding={h}
              notes={view.holdingNotes.get(h.symbol.toUpperCase())?.why}
              onSaveNotes={(sym, notes) => act.saveHoldingNotes(sym, notes, view.holdingNotes.get(sym.toUpperCase()))}
              onPlanExit={act.planExitFromHolding}
            />
          ))}
          {view.manualHolding.map((i) => <PlanCard key={i.item_id} item={i} quote={prices.get(symbolKey(i.symbol))} onUpdate={act.update} onDelete={act.remove} />)}
        </BoardLane>

        <BoardLane title="Exit Target" count={view.exits.length} badge="bg-amber-100 text-amber-800" onAdd={() => setAddLane('exit')}>
          {view.exits.map((i) => <PlanCard key={i.item_id} item={i} quote={prices.get(symbolKey(i.symbol))} onUpdate={act.update} onDelete={act.remove} />)}
        </BoardLane>
      </div>

      <AddBoardCardModal
        isOpen={addLane !== null}
        onClose={() => setAddLane(null)}
        ownerId={ownerId}
        defaultLane={addLane ?? 'watching'}
        onSuccess={() => queryClient.invalidateQueries({ queryKey: ['board', ownerId] })}
      />
    </div>
  );
};
