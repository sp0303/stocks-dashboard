import React, { Suspense, lazy, useState } from 'react';
import { KeyRound } from 'lucide-react';

const ChangePasswordModal = lazy(() =>
  import('@/features/auth/ChangePasswordModal').then((m) => ({ default: m.ChangePasswordModal })),
);

/** Header account action: opens the change-password dialog (POST /auth/change-password). */
export const AccountMenu: React.FC<{ onSignOut: () => void }> = ({ onSignOut }) => {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-canvas border border-hairline hover:bg-paper text-xs transition-colors"
        title="Change password"
        aria-label="Change password"
      >
        <KeyRound className="w-3.5 h-3.5" aria-hidden />
      </button>
      {open && (
        <Suspense fallback={null}>
          <ChangePasswordModal onClose={() => setOpen(false)} onSignOut={onSignOut} />
        </Suspense>
      )}
    </>
  );
};
