import React, { useState } from 'react';
import { X, ArrowRightLeft } from 'lucide-react';
import { reassignClientManager, type ClientSummary, type ManagerItem } from '@/lib/api';
import { useEscapeKey } from '@/lib/useEscapeKey';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  clients: ClientSummary[];
  managers: ManagerItem[];
  onSuccess: () => void;
}

export const ReassignClientModal: React.FC<Props> = ({ isOpen, onClose, clients, managers, onSuccess }) => {
  useEscapeKey(onClose, isOpen);
  const [selectedClientId, setSelectedClientId] = useState(clients[0]?.client_id || '');
  const [selectedManagerId, setSelectedManagerId] = useState(managers[0]?.manager_id || '');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedClientId || !selectedManagerId) return;
    setLoading(true);
    setError(null);
    try {
      await reassignClientManager(selectedClientId, selectedManagerId);
      onSuccess();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to reassign client');
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
          <ArrowRightLeft className="w-4 h-4 text-positive" /> Reassign Portfolio
        </h2>

        <form onSubmit={handleSubmit} className="space-y-3 text-sm">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-subtle mb-1">Select Client</label>
            <select
              value={selectedClientId}
              onChange={(e) => setSelectedClientId(e.target.value)}
              className="w-full p-2.5 rounded-xl border border-hairline bg-canvas text-ink text-sm"
            >
              {clients.map((c) => (
                <option key={c.client_id} value={c.client_id}>
                  {c.name} {c.client_code ? `(${c.client_code})` : ''}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-subtle mb-1">Assign to Manager</label>
            <select
              value={selectedManagerId}
              onChange={(e) => setSelectedManagerId(e.target.value)}
              className="w-full p-2.5 rounded-xl border border-hairline bg-canvas text-ink text-sm"
            >
              {managers.map((m) => (
                <option key={m.manager_id} value={m.manager_id}>
                  {m.name} {m.firm ? `(${m.firm})` : ''}
                </option>
              ))}
            </select>
          </div>

          {error && <p className="text-negative text-xs bg-negative/5 p-2 rounded-lg">{error}</p>}

          <button
            type="submit"
            disabled={!selectedClientId || !selectedManagerId || loading}
            className="w-full py-2.5 bg-ink text-paper rounded-xl font-semibold text-sm disabled:opacity-40"
          >
            {loading ? 'Reassigning...' : 'Confirm Reassignment'}
          </button>
        </form>
      </div>
    </div>
  );
};
