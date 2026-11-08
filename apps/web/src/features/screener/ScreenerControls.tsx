import React from 'react';
import { Search } from 'lucide-react';
import { SORT_LABELS, TOP_N, type SortKey } from './screenerUtils';

interface Props {
  sectors: string[];
  sector: string;
  sort: SortKey;
  top: number;
  q: string;
  onSector: (v: string) => void;
  onSort: (v: SortKey) => void;
  onTop: (v: number) => void;
  onQ: (v: string) => void;
}

const selCls = 'px-2.5 py-1.5 text-xs bg-canvas border border-hairline rounded-interactive text-ink focus:outline-none';

export const ScreenerControls: React.FC<Props> = ({ sectors, sector, sort, top, q, onSector, onSort, onTop, onQ }) => (
  <div className="flex flex-wrap items-center gap-2">
    <div className="inline-flex rounded-interactive border border-hairline overflow-hidden" role="group" aria-label="Top N">
      {TOP_N.map((n) => (
        <button
          key={n}
          type="button"
          aria-pressed={top === n}
          onClick={() => onTop(n)}
          className={`px-3 py-1.5 text-xs font-semibold ${top === n ? 'bg-ink text-paper' : 'bg-paper text-subtle hover:text-ink'}`}
        >
          Top {n}
        </button>
      ))}
    </div>
    <select aria-label="Sector" className={selCls} value={sector} onChange={(e) => onSector(e.target.value)} disabled={sectors.length === 0}>
      <option value="">All sectors</option>
      {sectors.map((s) => (
        <option key={s} value={s}>{s}</option>
      ))}
    </select>
    <select aria-label="Sort by" className={selCls} value={sort} onChange={(e) => onSort(e.target.value as SortKey)}>
      {(Object.keys(SORT_LABELS) as SortKey[]).map((k) => (
        <option key={k} value={k}>Sort: {SORT_LABELS[k]}</option>
      ))}
    </select>
    <div className="relative">
      <Search className="w-3.5 h-3.5 text-subtle absolute left-2.5 top-1/2 -translate-y-1/2" aria-hidden />
      <input
        aria-label="Search ticker or name"
        placeholder="Ticker / name"
        value={q}
        onChange={(e) => onQ(e.target.value)}
        className="pl-7 pr-3 py-1.5 text-xs bg-canvas border border-hairline rounded-interactive text-ink focus:outline-none focus:ring-1 focus:ring-ink"
      />
    </div>
  </div>
);
