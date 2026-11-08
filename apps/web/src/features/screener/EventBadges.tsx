import React from 'react';
import { formatRupees } from '@/lib/api';
import type { ScreenerEvent } from '@/lib/apiResearch';

const LABEL: Record<string, string> = {
  RESULTS: 'Results', DIVIDEND: 'Ex-div', BONUS: 'Bonus', SPLIT: 'Split', RIGHTS: 'Rights', BUYBACK: 'Buyback', DEMERGER: 'Demerger',
};

/** Upcoming results / ex-dates (text label + date, so colour is never the only signal). */
export const EventBadges: React.FC<{ events?: ScreenerEvent[] }> = ({ events }) => {
  if (!events || events.length === 0) return null;
  return (
    <span className="flex flex-wrap gap-1">
      {events.map((e) => (
        <span
          key={`${e.kind}-${e.date}`}
          title={e.amount != null ? `${formatRupees(e.amount)} per share` : undefined}
          className={`px-1.5 py-0.5 rounded-full border text-[10px] whitespace-nowrap ${e.kind === 'RESULTS' ? 'border-amber-300 bg-amber-50 text-ink dark:border-amber-700 dark:bg-amber-950/30' : 'border-hairline bg-canvas text-subtle'}`}
        >
          {LABEL[e.kind] ?? e.kind} {e.date.slice(5)}
        </span>
      ))}
    </span>
  );
};
