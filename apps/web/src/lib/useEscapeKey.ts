import { useEffect } from 'react';

/** Calls `onClose` when Escape is pressed while `enabled` (dialogs must be keyboard-closable, §5.13). */
export function useEscapeKey(onClose: () => void, enabled = true): void {
  useEffect(() => {
    if (!enabled) return undefined;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose, enabled]);
}
