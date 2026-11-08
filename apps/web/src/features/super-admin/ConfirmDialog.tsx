import React, { useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { useEscapeKey } from '@/lib/useEscapeKey';

interface Props {
  title: string;
  message: React.ReactNode;
  confirmLabel: string;
  /** Destructive actions use the negative token (DESIGN: ember only for destructive). */
  destructive?: boolean;
  onConfirm: () => Promise<unknown>;
  onClose: () => void;
}

/** Modal confirm with its own pending + error state; closes only on success. */
export const ConfirmDialog: React.FC<Props> = ({ title, message, confirmLabel, destructive, onConfirm, onClose }) => {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEscapeKey(onClose, !busy);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/40" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title">
      <div className="w-full max-w-sm bg-paper border border-hairline rounded-card p-6 shadow-xl space-y-4">
        <h2 id="confirm-title" className="text-base font-bold text-ink flex items-center gap-2">
          {destructive && <AlertTriangle className="w-4 h-4 text-negative" aria-hidden />} {title}
        </h2>
        <div className="text-sm text-subtle">{message}</div>
        {error && <p role="alert" className="text-xs text-negative bg-negative/5 border border-negative/30 p-2 rounded-interactive">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} disabled={busy} autoFocus={destructive} className="px-3.5 py-2 rounded-interactive border border-hairline text-xs font-semibold text-ink hover:bg-canvas">
            Cancel
          </button>
          <button
            type="button"
            onClick={run}
            disabled={busy}
            autoFocus={!destructive}
            className={`px-3.5 py-2 rounded-interactive text-xs font-semibold text-paper disabled:opacity-50 ${destructive ? 'bg-negative' : 'bg-ink'}`}
          >
            {busy ? 'Working…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
};
