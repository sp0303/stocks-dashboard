import React from 'react';
import { Plus } from 'lucide-react';

interface Props {
  title: string;
  count: number;
  badge: string;
  hint?: string;
  onAdd: () => void;
  children: React.ReactNode;
}

export const BoardLane: React.FC<Props> = ({ title, count, badge, hint, onAdd, children }) => (
  <section aria-label={title} className="bg-paper border border-hairline rounded-3xl p-4 shadow-sm space-y-3">
    <header className="flex items-center justify-between pb-2 border-b border-hairline">
      <div className="flex items-center gap-2">
        <h2 className="font-bold text-sm text-ink">{title}</h2>
        <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${badge}`}>{count}</span>
      </div>
      <button onClick={onAdd} title={`Add to ${title}`} className="p-1 rounded-lg text-subtle hover:text-ink hover:bg-canvas">
        <Plus className="w-4 h-4" />
      </button>
    </header>
    {hint && <p className="text-[10px] text-subtle">{hint}</p>}
    <div className="space-y-3 min-h-[140px]">
      {count === 0 ? (
        <div className="py-8 text-center text-xs text-subtle border border-dashed border-hairline rounded-xl">
          No cards in {title}
        </div>
      ) : (
        children
      )}
    </div>
  </section>
);
