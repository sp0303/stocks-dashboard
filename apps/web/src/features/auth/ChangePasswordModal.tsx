import React, { useState } from 'react';
import { KeyRound, X } from 'lucide-react';
import { ChangePasswordForm } from '@/features/auth/ChangePasswordForm';
import { useEscapeKey } from '@/lib/useEscapeKey';

interface Props {
  onClose: () => void;
  /** The API revokes every refresh token on success, so the user signs in again. */
  onSignOut: () => void;
}

export const ChangePasswordModal: React.FC<Props> = ({ onClose, onSignOut }) => {
  useEscapeKey(onClose);
  const [done, setDone] = useState(false);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-labelledby="pw-title" className="w-full max-w-sm bg-paper border border-hairline rounded-card shadow-xl p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 id="pw-title" className="flex items-center gap-2 text-base font-semibold text-ink">
            <KeyRound className="w-4 h-4" aria-hidden /> Change password
          </h2>
          <button type="button" onClick={onClose} aria-label="Close" className="p-1 rounded-interactive hover:bg-canvas text-subtle">
            <X className="w-4 h-4" aria-hidden />
          </button>
        </div>
        {done ? (
          <div className="space-y-4 text-sm text-ink" role="status">
            <p>Password changed. Every session was signed out; sign in again with the new password.</p>
            <button type="button" onClick={onSignOut} className="w-full py-2 rounded-interactive bg-ink text-paper font-semibold">Sign in again</button>
          </div>
        ) : (
          <ChangePasswordForm onDone={() => setDone(true)} />
        )}
      </div>
    </div>
  );
};
