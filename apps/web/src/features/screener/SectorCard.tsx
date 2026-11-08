import React from 'react';
import { formatPercent } from '@/lib/api';
import type { SectorSummary } from './screenerUtils';
import { visibleSetup } from './screenerUtils';

interface Props {
  s: SectorSummary;
}

const tone = (v: number | null) => (v == null || v === 0 ? 'text-ink' : v > 0 ? 'text-positive' : 'text-negative');

export const SectorCard: React.FC<Props> = React.memo(({ s }) => (
  <article className="bg-paper border border-hairline rounded-card p-5 shadow-sm space-y-3" aria-label={`${s.sector} sector`}>
    <header className="flex items-start justify-between gap-2">
      <div>
        <h2 className="text-sm font-bold text-ink">{s.sector}</h2>
        <div className="text-[11px] text-subtle">
          {s.count} stocks{s.setups > 0 ? ` · ${s.setups} with a setup` : ''}
        </div>
      </div>
      <div className="text-right">
        <div className="text-[10px] uppercase font-semibold text-subtle">Avg score</div>
        <div className="text-sm font-bold font-mono text-ink">{s.avgScore != null ? s.avgScore.toFixed(1) : '—'}</div>
      </div>
    </header>
    <dl className="grid grid-cols-3 gap-2 text-center">
      {(['d1', 'w1', 'm1'] as const).map((k) => (
        <div key={k} className="bg-canvas rounded-interactive border border-hairline py-1.5">
          <dt className="text-[10px] uppercase font-semibold text-subtle">{k === 'd1' ? '1D' : k === 'w1' ? '1W' : '1M'}</dt>
          <dd className={`text-xs font-mono font-semibold ${tone(s.avg[k])}`}>{formatPercent(s.avg[k], 1)}</dd>
        </div>
      ))}
    </dl>
    <ol className="space-y-1">
      {s.leaders.map((r, i) => (
        <li key={`${r.symbol}-${i}`} className="flex items-center justify-between text-xs">
          <span className="font-semibold text-ink">
            {r.symbol}
            {visibleSetup(r.setup) && <span className="ml-1.5 text-[10px] text-subtle">({visibleSetup(r.setup)})</span>}
          </span>
          <span className="font-mono text-subtle">{r.score != null ? r.score.toFixed(1) : '—'}</span>
        </li>
      ))}
    </ol>
  </article>
));
SectorCard.displayName = 'SectorCard';
