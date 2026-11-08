import React from 'react';
import { formatPercent, formatRupees } from '@/lib/api';
import type { ScreenerRow } from '@/lib/apiResearch';
import { visibleSetup } from './screenerUtils';
import { EventBadges } from './EventBadges';

interface Props {
  rows: ScreenerRow[];
}

const HEAD: Array<[string, boolean]> = [
  ['#', false], ['Symbol', false], ['Sector', false], ['Price', true], ['1D', true], ['1W', true], ['1M', true],
  ['Score', true], ['Setup', false], ['Typical hold', true], ['Events', false],
];

const tone = (v: number | null | undefined) => (v == null || v === 0 ? 'text-ink' : v > 0 ? 'text-positive' : 'text-negative');

const Row: React.FC<{ r: ScreenerRow; i: number }> = React.memo(({ r, i }) => {
  const setup = visibleSetup(r.setup);
  return (
    <tr className="hover:bg-canvas/50">
      <td className="py-2.5 px-3 text-xs text-subtle font-mono">{i + 1}</td>
      <td className="py-2.5 px-3 text-xs font-bold text-ink">
        {r.symbol}
        {r.name && <div className="text-[10px] font-normal text-subtle truncate max-w-[160px]">{r.name}</div>}
      </td>
      <td className="py-2.5 px-3 text-xs text-subtle">{r.sector ?? '—'}</td>
      <td className="py-2.5 px-3 text-right font-mono text-xs">{formatRupees(r.price)}</td>
      <td className={`py-2.5 px-3 text-right font-mono text-xs ${tone(r.d1)}`}>{formatPercent(r.d1, 1)}</td>
      <td className={`py-2.5 px-3 text-right font-mono text-xs ${tone(r.w1)}`}>{formatPercent(r.w1, 1)}</td>
      <td className={`py-2.5 px-3 text-right font-mono text-xs ${tone(r.m1)}`}>{formatPercent(r.m1, 1)}</td>
      <td className="py-2.5 px-3 text-right font-mono text-xs font-semibold">{r.score != null ? r.score.toFixed(1) : '—'}</td>
      <td className="py-2.5 px-3 text-xs">
        {setup && <span className="px-2 py-0.5 rounded-full border border-hairline bg-canvas text-ink text-[11px]">{setup}</span>}
      </td>
      <td className="py-2.5 px-3 text-right text-xs text-subtle">
        {r.typical_hold_days != null ? `~${Math.round(r.typical_hold_days)} sessions` : ''}
      </td>
      <td className="py-2.5 px-3 text-xs"><EventBadges events={r.events} /></td>
    </tr>
  );
});
Row.displayName = 'ScreenerRow';

/** Max 100 rows (Top-N), so no virtualisation needed beyond memoised rows. */
export const ScreenerTable: React.FC<Props> = ({ rows }) => (
  <div className="overflow-x-auto">
    <table className="w-full text-left border-collapse text-sm" aria-label="Screener results">
      <thead>
        <tr className="bg-canvas/60 text-subtle text-xs border-b border-hairline">
          {HEAD.map(([h, right]) => (
            <th key={h} className={`py-2.5 px-3 font-semibold ${right ? 'text-right' : ''}`}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-hairline">
        {rows.map((r, i) => (
          <Row key={`${r.symbol}-${i}`} r={r} i={i} />
        ))}
      </tbody>
    </table>
  </div>
);
