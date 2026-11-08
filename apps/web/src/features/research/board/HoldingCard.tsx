import React, { useState } from 'react';
import { ChevronDown, ChevronRight, LogOut } from 'lucide-react';
import { formatRupees, type ManagerHoldingsItem } from '@/lib/api';
import { PriceLine } from './PriceLine';

interface Props {
  holding: ManagerHoldingsItem;
  /** Free-text notes kept on a holding-lane board card for this symbol (as v1 did). */
  notes?: string | null;
  onSaveNotes: (symbol: string, notes: string) => void;
  onPlanExit: (holding: ManagerHoldingsItem) => void;
}

/** A real position summed across the selected clients (R5), priced at the latest close. */
export const HoldingCard: React.FC<Props> = ({ holding: h, notes, onSaveNotes, onPlanExit }) => {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(notes ?? '');

  const save = () => {
    setEditing(false);
    if (draft !== (notes ?? '')) onSaveNotes(h.symbol, draft);
  };

  return (
    <div className="p-3.5 bg-paper border border-hairline rounded-xl shadow-sm space-y-2">
      <div className="flex items-center justify-between">
        <span className="font-bold text-ink font-mono text-sm">{h.symbol}</span>
        <span className="text-[10px] text-subtle">{h.exchange}</span>
      </div>
      <PriceLine
        price={h.current_price}
        asOf={h.price_as_of}
        change={h.return_pct}
        amount={h.unrealized_pnl}
        changeLabel="vs cost"
      />
      <div className="text-[11px] text-subtle font-mono">
        {h.quantity.toLocaleString('en-IN')} sh · avg {formatRupees(h.avg_cost)}
      </div>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex items-center gap-1 text-[11px] text-subtle hover:text-ink"
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        {h.client_count} client{h.client_count === 1 ? '' : 's'}
      </button>
      {open && (
        <ul className="text-[11px] text-ink bg-canvas rounded-lg p-2 space-y-0.5">
          {(h.clients ?? []).map((c) => (
            <li key={c.client_id} className="flex justify-between gap-2">
              <span className="truncate">{c.name}</span>
              <span className="font-mono">{c.quantity.toLocaleString('en-IN')}</span>
            </li>
          ))}
        </ul>
      )}
      {editing ? (
        <textarea
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={save}
          rows={2}
          placeholder="Your notes"
          className="w-full text-xs p-2 rounded-lg border border-hairline bg-canvas"
        />
      ) : (
        <button onClick={() => setEditing(true)} className="w-full text-left text-[11px] text-subtle hover:text-ink">
          {notes ? <span className="italic">{notes}</span> : '+ Add notes'}
        </button>
      )}
      <div className="pt-1 border-t border-hairline flex justify-end">
        <button
          onClick={() => onPlanExit(h)}
          className="flex items-center gap-1 px-2 py-0.5 rounded-md border border-hairline bg-canvas text-subtle hover:text-ink text-[10px]"
        >
          <LogOut className="w-3 h-3" /> Plan exit
        </button>
      </div>
    </div>
  );
};
