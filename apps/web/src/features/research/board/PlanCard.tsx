import React, { useState } from 'react';
import { Trash2 } from 'lucide-react';
import { formatRupees, type BoardItemResponse, type BoardItemUpdate } from '@/lib/api';
import type { PriceQuote } from '@/lib/apiResearch';
import { PriceLine } from './PriceLine';
import { ColourDots } from './ColourDots';
import { colourClass, pctVsEntry, type Lane } from './boardMath';

interface Props {
  item: BoardItemResponse;
  quote?: PriceQuote;
  onUpdate: (itemId: string, patch: BoardItemUpdate) => void;
  onDelete: (itemId: string) => void;
}

const LANES: Lane[] = ['watching', 'holding', 'exit'];
const num = (v: string) => (v.trim() === '' ? null : Number(v));

/** A manual idea or exit plan: latest close, % vs planned entry, editable plan + thesis. */
export const PlanCard: React.FC<Props> = ({ item, quote, onUpdate, onDelete }) => {
  const [editingPlan, setEditingPlan] = useState(false);
  const [entry, setEntry] = useState(item.entry_price?.toString() ?? '');
  const [exit, setExit] = useState(item.exit_price?.toString() ?? '');
  const [why, setWhy] = useState(item.why ?? '');

  const savePlan = () => {
    setEditingPlan(false);
    onUpdate(item.item_id, { entry_price: num(entry), exit_price: num(exit) });
  };
  const saveWhy = () => {
    if (why !== (item.why ?? '')) onUpdate(item.item_id, { why });
  };

  return (
    <div className={`p-3.5 border rounded-xl shadow-sm space-y-2 ${colourClass(item.colour)}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-bold text-ink font-mono text-sm">{item.symbol}</span>
        <div className="flex items-center gap-2">
          <ColourDots value={item.colour} onPick={(c) => onUpdate(item.item_id, { colour: c })} />
          <button onClick={() => onDelete(item.item_id)} title="Remove card" className="p-1 rounded text-subtle hover:text-ember">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
      <PriceLine
        price={quote?.price}
        asOf={quote?.price_date}
        stale={quote?.is_stale}
        change={pctVsEntry(quote?.price, item.entry_price)}
        changeLabel="vs plan entry"
      />
      {editingPlan ? (
        <div className="flex items-center gap-1 text-xs">
          <input aria-label="Entry" type="number" value={entry} onChange={(e) => setEntry(e.target.value)} placeholder="Entry" className="w-20 px-2 py-1 rounded border border-hairline bg-canvas" />
          <span className="text-subtle">→</span>
          <input aria-label="Exit" type="number" value={exit} onChange={(e) => setExit(e.target.value)} placeholder="Exit" className="w-20 px-2 py-1 rounded border border-hairline bg-canvas" />
          <button onClick={savePlan} className="px-2 py-1 rounded bg-ink text-paper">✓</button>
        </div>
      ) : (
        <button onClick={() => setEditingPlan(true)} title="Edit plan" className="text-[11px] font-mono text-subtle hover:text-ink">
          Entry {formatRupees(item.entry_price)} → Exit {formatRupees(item.exit_price)}
        </button>
      )}
      <textarea
        aria-label="Why (thesis)"
        value={why}
        onChange={(e) => setWhy(e.target.value)}
        onBlur={saveWhy}
        rows={2}
        placeholder="Why? (thesis)"
        className="w-full text-xs p-2 rounded-lg border border-hairline bg-canvas"
      />
      <div className="pt-1 flex items-center justify-end gap-1 border-t border-hairline">
        {LANES.filter((l) => l !== item.lane).map((l) => (
          <button key={l} onClick={() => onUpdate(item.item_id, { lane: l })} className="px-2 py-0.5 rounded-md border border-hairline bg-canvas text-subtle hover:text-ink capitalize text-[10px]">
            → {l}
          </button>
        ))}
      </div>
    </div>
  );
};
