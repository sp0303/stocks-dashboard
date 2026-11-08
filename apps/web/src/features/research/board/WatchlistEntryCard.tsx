import React from 'react';
import { LogOut } from 'lucide-react';
import { formatRupees, type WatchlistEntryItem } from '@/lib/api';
import type { PriceQuote } from '@/lib/apiResearch';
import { PriceLine } from './PriceLine';
import { pctVsEntry } from './boardMath';

interface Props {
  entry: WatchlistEntryItem;
  listName: string;
  quote?: PriceQuote;
  onPlanExit: (entry: WatchlistEntryItem) => void;
}

/** A stock pulled into Watching from a selected watchlist: latest close vs the price when added. */
export const WatchlistEntryCard: React.FC<Props> = ({ entry, listName, quote, onPlanExit }) => (
  <div className="p-3.5 bg-paper border border-dashed border-hairline rounded-xl space-y-2">
    <div className="flex items-center justify-between">
      <span className="font-bold text-ink font-mono text-sm">{entry.symbol}</span>
      <span className="text-[10px] text-subtle truncate max-w-[50%]" title={listName}>★ {listName}</span>
    </div>
    <PriceLine
      price={quote?.price}
      asOf={quote?.price_date}
      change={pctVsEntry(quote?.price, entry.added_price)}
      changeLabel="since added"
    />
    <div className="text-[11px] text-subtle font-mono">
      Added {formatRupees(entry.added_price)} on {entry.added_date}
    </div>
    {entry.why && <p className="text-xs text-subtle line-clamp-2">{entry.why}</p>}
    <div className="pt-1 border-t border-hairline flex justify-end">
      <button
        onClick={() => onPlanExit(entry)}
        className="flex items-center gap-1 px-2 py-0.5 rounded-md border border-hairline bg-canvas text-subtle hover:text-ink text-[10px]"
      >
        <LogOut className="w-3 h-3" /> Plan exit
      </button>
    </div>
  </div>
);
