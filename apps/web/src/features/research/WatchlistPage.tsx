import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Bookmark, Plus, FolderPlus } from 'lucide-react';
import { fetchWatchlists, deleteWatchlistEntry, type WatchlistResponse } from '@/lib/api';
import { ErrorBlock, LoadingBlock } from '@/components/QueryStates';
import { useAuthStore } from '@/stores/authStore';
import { AddSymbolModal } from './AddSymbolModal';
import { CreateWatchlistModal } from './CreateWatchlistModal';
import { WatchlistTable } from './WatchlistTable';

export const WatchlistPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { managerId, impersonatedManagerId } = useAuthStore();
  // Match ManagerBook: a super-admin impersonating a manager must see that manager's data.
  const ownerId = impersonatedManagerId || managerId || '00000000-0000-0000-0000-000000000000';

  const [activeWatchlistId, setActiveWatchlistId] = useState<string | null>(null);
  const [isAddSymbolOpen, setIsAddSymbolOpen] = useState(false);
  const [isCreateWatchlistOpen, setIsCreateWatchlistOpen] = useState(false);

  const { data: watchlists, isLoading, error, refetch } = useQuery<WatchlistResponse[]>({
    queryKey: ['watchlists', ownerId],
    queryFn: () => fetchWatchlists(ownerId),
  });

  const activeWatchlist = watchlists?.find((w) => w.watchlist_id === activeWatchlistId) ?? watchlists?.[0];

  const handleDeleteEntry = async (symbol: string) => {
    if (!activeWatchlist) return;
    try {
      await deleteWatchlistEntry(activeWatchlist.watchlist_id, symbol);
      queryClient.invalidateQueries({ queryKey: ['watchlists', ownerId] });
    } catch (e) {
      console.error('Failed to delete entry', e);
    }
  };

  if (isLoading) {
    return <LoadingBlock rows={5} label="Loading watchlists" />;
  }

  if (error) {
    return <ErrorBlock message={(error as Error).message || 'Failed to load watchlists.'} onRetry={() => refetch()} />;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Bookmark className="w-5 h-5 text-positive" />
          <h1 className="text-xl font-bold text-ink">Watchlists</h1>
          {watchlists && watchlists.length > 0 && (
            <select
              value={activeWatchlist?.watchlist_id}
              onChange={(e) => setActiveWatchlistId(e.target.value)}
              className="px-3 py-1.5 rounded-xl border border-hairline bg-paper text-ink text-sm font-semibold"
            >
              {watchlists.map((w) => (
                <option key={w.watchlist_id} value={w.watchlist_id}>
                  {w.name} ({w.entries.length})
                </option>
              ))}
            </select>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsCreateWatchlistOpen(true)}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-hairline bg-paper text-xs font-semibold text-ink hover:bg-canvas transition-colors"
          >
            <FolderPlus className="w-4 h-4 text-subtle" /> New List
          </button>
          {activeWatchlist && (
            <button
              onClick={() => setIsAddSymbolOpen(true)}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-ink text-paper text-xs font-semibold hover:bg-ink/90 transition-colors"
            >
              <Plus className="w-4 h-4" /> Add Symbol
            </button>
          )}
        </div>
      </div>

      {activeWatchlist && <WatchlistTable watchlist={activeWatchlist} onDelete={handleDeleteEntry} />}

      {(!watchlists || watchlists.length === 0) && (
        <div className="bg-paper border border-hairline rounded-2xl p-12 text-center text-subtle text-sm">
          No watchlists found. Create your first watchlist to begin tracking ideas!
        </div>
      )}

      {activeWatchlist && (
        <AddSymbolModal
          isOpen={isAddSymbolOpen}
          onClose={() => setIsAddSymbolOpen(false)}
          watchlistId={activeWatchlist.watchlist_id}
          onSuccess={() => queryClient.invalidateQueries({ queryKey: ['watchlists', ownerId] })}
        />
      )}

      <CreateWatchlistModal
        isOpen={isCreateWatchlistOpen}
        onClose={() => setIsCreateWatchlistOpen(false)}
        ownerId={ownerId}
        onSuccess={() => queryClient.invalidateQueries({ queryKey: ['watchlists', ownerId] })}
      />
    </div>
  );
};
