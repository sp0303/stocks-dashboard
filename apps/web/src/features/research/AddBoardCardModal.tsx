import React, { useState } from 'react';
import { X, Plus } from 'lucide-react';
import { createBoardItem, type BoardItemCreate } from '@/lib/api';
import { useEscapeKey } from '@/lib/useEscapeKey';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  ownerId: string;
  defaultLane: 'watching' | 'holding' | 'exit';
  onSuccess: () => void;
}

export const AddBoardCardModal: React.FC<Props> = ({ isOpen, onClose, ownerId, defaultLane, onSuccess }) => {
  useEscapeKey(onClose, isOpen);
  const [symbol, setSymbol] = useState('');
  const [lane, setLane] = useState<'watching' | 'holding' | 'exit'>(defaultLane);
  const [entryPrice, setEntryPrice] = useState('');
  const [exitPrice, setExitPrice] = useState('');
  const [why, setWhy] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!symbol.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const item: BoardItemCreate = {
        owner_type: 'MANAGER',
        owner_id: ownerId,
        symbol: symbol.trim().toUpperCase(),
        lane,
        entry_price: entryPrice ? parseFloat(entryPrice) : null,
        exit_price: exitPrice ? parseFloat(exitPrice) : null,
        why: why.trim() || null,
      };
      await createBoardItem(item);
      onSuccess();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create card');
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
          <Plus className="w-4 h-4 text-positive" /> Add Card to {lane.toUpperCase()}
        </h2>

        <form onSubmit={handleSubmit} className="space-y-3 text-sm">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-subtle mb-1">Symbol *</label>
            <input
              type="text"
              required
              placeholder="e.g. INFOSYS"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              className="w-full p-2.5 rounded-xl border border-hairline bg-canvas text-ink text-sm uppercase"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-subtle mb-1">Lane</label>
            <select
              value={lane}
              onChange={(e) => setLane(e.target.value as 'watching' | 'holding' | 'exit')}
              className="w-full p-2.5 rounded-xl border border-hairline bg-canvas text-ink text-sm capitalize"
            >
              <option value="watching">Watching (Pipeline)</option>
              <option value="holding">Holding (Active)</option>
              <option value="exit">Exit (Target / Stop)</option>
            </select>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-subtle mb-1">Entry Price</label>
              <input
                type="number"
                step="any"
                placeholder="₹"
                value={entryPrice}
                onChange={(e) => setEntryPrice(e.target.value)}
                className="w-full p-2.5 rounded-xl border border-hairline bg-canvas text-ink text-sm font-mono"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-subtle mb-1">Exit / Target</label>
              <input
                type="number"
                step="any"
                placeholder="₹"
                value={exitPrice}
                onChange={(e) => setExitPrice(e.target.value)}
                className="w-full p-2.5 rounded-xl border border-hairline bg-canvas text-ink text-sm font-mono"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-subtle mb-1">Thesis / Why</label>
            <textarea
              rows={2}
              placeholder="Setup, triggers, conviction note..."
              value={why}
              onChange={(e) => setWhy(e.target.value)}
              className="w-full p-2.5 rounded-xl border border-hairline bg-canvas text-ink text-sm resize-none"
            />
          </div>

          {error && <p className="text-ember text-xs bg-ember/10 p-2 rounded-lg">{error}</p>}

          <button
            type="submit"
            disabled={!symbol || loading}
            className="w-full py-2.5 bg-ink text-paper rounded-xl font-semibold text-sm disabled:opacity-40"
          >
            {loading ? 'Adding...' : 'Add Card'}
          </button>
        </form>
      </div>
    </div>
  );
};
