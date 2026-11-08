import React from 'react';
import { Trash2 } from 'lucide-react';
import { formatPercent, formatRupees, type WatchlistEntryItem } from '@/lib/api';
import type { PriceQuote } from '@/lib/apiResearch';
import { pctToAlert, pctVsEntry } from './board/boardMath';

interface Props {
  entry: WatchlistEntryItem;
  quote?: PriceQuote;
  onDelete: (symbol: string) => void;
}

const tone = (v: number | null) => (v == null || v === 0 ? 'text-ink' : v > 0 ? 'text-positive' : 'text-negative');
const cell = 'py-3 px-4';

/** One watchlist entry: last close (as_of, stale flag), change vs entry, distance to alert. */
export const WatchlistRow: React.FC<Props> = React.memo(({ entry, quote, onDelete }) => {
  const price = quote?.price ?? null;
  const vsEntry = pctVsEntry(price, entry.added_price);
  const toAlert = pctToAlert(price, entry.alert_price);
  return (
    <tr className="hover:bg-canvas/50 transition-colors">
      <td className={`${cell} font-bold text-ink font-mono`}>{entry.symbol}</td>
      <td className={`${cell} text-subtle text-xs`}>{entry.sector || '—'}</td>
      <td className={`${cell} text-right font-mono text-xs`}>
        {price == null ? (
          <span className="italic text-subtle">unpriced</span>
        ) : (
          <>
            <div className="text-ink">{formatRupees(price)}</div>
            <div className={`text-[10px] ${quote?.is_stale ? 'text-amber-600 dark:text-amber-400 font-semibold' : 'text-subtle'}`}>
              {quote?.is_stale ? 'stale · ' : ''}{quote?.price_date}
            </div>
          </>
        )}
      </td>
      <td className={`${cell} text-right text-ink font-mono text-xs`}>{formatRupees(entry.added_price)}</td>
      <td className={`${cell} text-right font-mono text-xs ${tone(vsEntry)}`}>{formatPercent(vsEntry, 1)}</td>
      <td className={`${cell} text-right font-mono text-xs`}>
        <div className="text-ink">{formatRupees(entry.alert_price)}</div>
        {toAlert != null && (
          <div className="text-[10px] text-subtle">{toAlert === 0 ? 'at alert' : `${formatPercent(toAlert, 1)} to go`}</div>
        )}
      </td>
      <td className={`${cell} text-subtle text-xs max-w-xs truncate`} title={entry.why ?? undefined}>{entry.why || '—'}</td>
      <td className={`${cell} text-right`}>
        <button
          type="button"
          onClick={() => onDelete(entry.symbol)}
          className="p-1 rounded-lg text-subtle hover:text-negative hover:bg-negative/10 transition-colors"
          title="Remove symbol"
          aria-label={`Remove ${entry.symbol}`}
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </td>
    </tr>
  );
});
WatchlistRow.displayName = 'WatchlistRow';
