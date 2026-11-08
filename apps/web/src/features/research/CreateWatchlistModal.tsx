import React, { useState } from 'react';
import { X, FolderPlus } from 'lucide-react';
import { createWatchlist } from '@/lib/api';
import { useEscapeKey } from '@/lib/useEscapeKey';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  ownerId: string;
  onSuccess: () => void;
}

export const CreateWatchlistModal: React.FC<Props> = ({ isOpen, onClose, ownerId, onSuccess }) => {
  useEscapeKey(onClose, isOpen);
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await createWatchlist({
        owner_type: 'MANAGER',
        owner_id: ownerId,
        name: name.trim(),
        is_default: false,
      });
      onSuccess();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create watchlist');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/40 backdrop-blur-sm" role="dialog" aria-modal="true">
      <div className="w-full max-w-sm bg-paper border border-hairline rounded-2xl p-6 shadow-xl relative">
        <button onClick={onClose} className="absolute top-4 right-4 text-subtle hover:text-ink p-1">
          <X className="w-5 h-5" />
        </button>
        <h2 className="text-base font-bold text-ink mb-4 flex items-center gap-2">
          <FolderPlus className="w-4 h-4 text-positive" /> New Watchlist
        </h2>

        <form onSubmit={handleSubmit} className="space-y-3 text-sm">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-subtle mb-1">Watchlist Name *</label>
            <input
              type="text"
              required
              placeholder="e.g. High Growth, Dividend Aristocrats"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full p-2.5 rounded-xl border border-hairline bg-canvas text-ink text-sm"
            />
          </div>

          {error && <p className="text-ember text-xs bg-ember/10 p-2 rounded-lg">{error}</p>}

          <button
            type="submit"
            disabled={!name.trim() || loading}
            className="w-full py-2.5 bg-ink text-paper rounded-xl font-semibold text-sm disabled:opacity-40"
          >
            {loading ? 'Creating...' : 'Create Watchlist'}
          </button>
        </form>
      </div>
    </div>
  );
};
