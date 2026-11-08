import React, { useState } from 'react';
import { X } from 'lucide-react';
import type { ManagerItem } from '@/lib/api';
import { updateManager } from '@/lib/apiAdmin';
import { useEscapeKey } from '@/lib/useEscapeKey';

interface Props {
  manager: ManagerItem;
  onClose: () => void;
  onSaved: () => void;
}

const FIELD = 'w-full p-2.5 rounded-interactive border border-hairline bg-canvas text-ink text-sm';

export const EditManagerModal: React.FC<Props> = ({ manager, onClose, onSaved }) => {
  useEscapeKey(onClose);
  const [name, setName] = useState(manager.name);
  const [email, setEmail] = useState(manager.email);
  const [firm, setFirm] = useState(manager.firm ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await updateManager(manager.manager_id, {
        name: name.trim(),
        firm: firm.trim(),
        email: email.trim() !== manager.email ? email.trim() : undefined,
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/40" role="dialog" aria-modal="true" aria-labelledby="edit-mgr">
      <form onSubmit={submit} className="w-full max-w-sm bg-paper border border-hairline rounded-card p-6 shadow-xl relative space-y-3 text-sm">
        <button type="button" onClick={onClose} aria-label="Close" className="absolute top-4 right-4 text-subtle hover:text-ink p-1">
          <X className="w-5 h-5" />
        </button>
        <h2 id="edit-mgr" className="text-base font-bold text-ink">Edit manager</h2>
        <label className="block text-xs font-semibold text-subtle">
          Name
          <input required value={name} onChange={(e) => setName(e.target.value)} className={`${FIELD} mt-1`} />
        </label>
        <label className="block text-xs font-semibold text-subtle">
          Email (also the login)
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={`${FIELD} mt-1`} />
        </label>
        <label className="block text-xs font-semibold text-subtle">
          Firm / desk
          <input value={firm} onChange={(e) => setFirm(e.target.value)} className={`${FIELD} mt-1`} />
        </label>
        {error && <p role="alert" className="text-negative text-xs">{error}</p>}
        <button type="submit" disabled={busy || !name.trim()} className="w-full py-2.5 bg-ink text-paper rounded-interactive font-semibold disabled:opacity-40">
          {busy ? 'Saving…' : 'Save changes'}
        </button>
      </form>
    </div>
  );
};
