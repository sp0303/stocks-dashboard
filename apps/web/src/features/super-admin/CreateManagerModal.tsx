import React, { useState } from 'react';
import { X, UserPlus } from 'lucide-react';
import { createAdminManager } from '@/lib/api';
import { useEscapeKey } from '@/lib/useEscapeKey';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const CreateManagerModal: React.FC<Props> = ({ isOpen, onClose, onSuccess }) => {
  useEscapeKey(onClose, isOpen);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [firm, setFirm] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !email.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await createAdminManager({
        name: name.trim(),
        email: email.trim(),
        firm: firm.trim() || undefined,
        password: password.trim() || undefined,
      });
      onSuccess();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create manager');
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
          <UserPlus className="w-4 h-4 text-positive" /> Add Investment Manager
        </h2>

        <form onSubmit={handleSubmit} className="space-y-3 text-sm">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-subtle mb-1">Full Name *</label>
            <input
              type="text"
              required
              placeholder="e.g. Anand Rathi"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full p-2.5 rounded-xl border border-hairline bg-canvas text-ink text-sm"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-subtle mb-1">Email Address *</label>
            <input
              type="email"
              required
              placeholder="manager@firm.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full p-2.5 rounded-xl border border-hairline bg-canvas text-ink text-sm"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-subtle mb-1">Firm / Desk</label>
            <input
              type="text"
              placeholder="e.g. Wealth Advisors"
              value={firm}
              onChange={(e) => setFirm(e.target.value)}
              className="w-full p-2.5 rounded-xl border border-hairline bg-canvas text-ink text-sm"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-subtle mb-1">Initial Password</label>
            <input
              type="password"
              placeholder="Optional login password (min 8 chars)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full p-2.5 rounded-xl border border-hairline bg-canvas text-ink text-sm"
            />
          </div>

          {error && <p className="text-negative text-xs bg-negative/5 p-2 rounded-lg">{error}</p>}

          <button
            type="submit"
            disabled={!name || !email || loading}
            className="w-full py-2.5 bg-ink text-paper rounded-xl font-semibold text-sm disabled:opacity-40"
          >
            {loading ? 'Creating...' : 'Create Manager Account'}
          </button>
        </form>
      </div>
    </div>
  );
};
