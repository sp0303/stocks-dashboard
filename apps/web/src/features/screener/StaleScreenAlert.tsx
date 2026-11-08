import React from 'react';
import { AlertTriangle } from 'lucide-react';

interface Props {
  asOf: string | null | undefined;
  sessionsBehind?: number | null;
}

/** Shown when the snapshot's close is more than one trading session old. */
export const StaleScreenAlert: React.FC<Props> = ({ asOf, sessionsBehind }) => (
  <div role="alert" className="flex items-center gap-2 p-3 text-xs rounded-interactive border border-amber-300 bg-amber-50 text-ink dark:border-amber-700 dark:bg-amber-950/30">
    <AlertTriangle className="w-4 h-4 shrink-0" aria-hidden />
    <span>
      Stale screen: built from the close of <strong>{asOf ?? 'unknown'}</strong>
      {sessionsBehind != null ? `, ${sessionsBehind} sessions behind` : ''}. Check the daily screener sync.
    </span>
  </div>
);
