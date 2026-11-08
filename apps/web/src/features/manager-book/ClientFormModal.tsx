import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { X } from 'lucide-react';
import { fetchManagers, type BookRosterItem, type Broker, type ClientInput } from '@/lib/apiAdmin';
import { useAuthStore } from '@/stores/authStore';
import { useEscapeKey } from '@/lib/useEscapeKey';

interface Props {
  managerId: string;
  client?: BookRosterItem;
  onSubmit: (data: ClientInput) => Promise<unknown>;
  onClose: () => void;
}

const BROKERS: Broker[] = ['ZERODHA', 'UPSTOX', 'ANGEL', 'OTHER'];
const FIELD = 'mt-1 w-full p-2.5 rounded-interactive border border-hairline bg-canvas text-ink text-sm';

/** Add / edit a client: name, broker + code, and (super-admin only) the manager. */
export const ClientFormModal: React.FC<Props> = ({ managerId, client, onSubmit, onClose }) => {
  useEscapeKey(onClose);
  const isAdmin = useAuthStore((s) => s.role) === 'super_admin';
  const managers = useQuery({ queryKey: ['admin', 'managers'], queryFn: fetchManagers, enabled: isAdmin });
  const [name, setName] = useState(client?.name ?? '');
  const [code, setCode] = useState(client?.client_code ?? '');
  const [broker, setBroker] = useState<Broker | ''>(client?.broker ?? '');
  const [mgr, setMgr] = useState(managerId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const data: ClientInput = { name: name.trim(), client_code: code.trim() || null, broker: broker || null };
      if (isAdmin && mgr !== managerId) data.manager_id = mgr;
      await onSubmit(data);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/40" role="dialog" aria-modal="true" aria-labelledby="client-form">
      <form onSubmit={submit} className="w-full max-w-sm bg-paper border border-hairline rounded-card p-6 shadow-xl relative space-y-3 text-sm">
        <button type="button" onClick={onClose} aria-label="Close" className="absolute top-4 right-4 text-subtle hover:text-ink p-1"><X className="w-5 h-5" /></button>
        <h2 id="client-form" className="text-base font-bold text-ink">{client ? 'Edit client' : 'Add client'}</h2>
        <label className="block text-xs font-semibold text-subtle">Name *<input required value={name} onChange={(e) => setName(e.target.value)} className={FIELD} /></label>
        <label className="block text-xs font-semibold text-subtle">
          Broker
          <select value={broker} onChange={(e) => setBroker(e.target.value as Broker | '')} className={FIELD}>
            <option value="">—</option>
            {BROKERS.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </label>
        <label className="block text-xs font-semibold text-subtle">Broker client code<input value={code} onChange={(e) => setCode(e.target.value)} className={FIELD} /></label>
        {isAdmin && (
          <label className="block text-xs font-semibold text-subtle">
            Manager
            <select value={mgr} onChange={(e) => setMgr(e.target.value)} className={FIELD}>
              {(managers.data ?? []).filter((m) => m.is_active || m.manager_id === managerId).map((m) => <option key={m.manager_id} value={m.manager_id}>{m.name}</option>)}
              {!managers.data && <option value={managerId}>Current manager</option>}
            </select>
          </label>
        )}
        {error && <p role="alert" className="text-negative text-xs">{error}</p>}
        <button type="submit" disabled={busy || !name.trim()} className="w-full py-2.5 bg-ink text-paper rounded-interactive font-semibold disabled:opacity-40">{busy ? 'Saving…' : client ? 'Save changes' : 'Add client'}</button>
      </form>
    </div>
  );
};
