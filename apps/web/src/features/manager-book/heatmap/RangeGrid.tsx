import React, { memo } from 'react';
import { formatPercent, formatRupees } from '@/lib/api';
import type { HeatmapResponse, HeatmapRow } from '@/lib/apiHeatmap';
import { CAP, colLabel, shade } from './heatShade';

type Col = HeatmapResponse['columns'][number];
type Grain = keyof typeof CAP;

const Row: React.FC<{ r: HeatmapRow; cols: Col[]; grain: Grain }> = memo(({ r, cols, grain }) => (
  <tr>
    <th scope="row" className="sticky left-0 z-10 bg-paper text-left px-2 py-1 font-semibold whitespace-nowrap" title={`Invested ${formatRupees(r.invested, 0)} · ${r.clients} client(s)`}>
      {r.symbol}{r.suspect ? ' ⚠' : ''}
      <span className="block text-[10px] font-normal text-subtle">{r.start ?? '—'}</span>
    </th>
    {cols.map((c) => {
      const v = r.cells[c.key];
      return (
        <td key={c.key} className="px-1.5 py-1 text-right tabular-nums" style={shade(v, CAP[grain])} title={`${r.symbol} ${c.key}: ${formatPercent(v)}`}>
          {v == null ? '' : formatPercent(v, 1)}
        </td>
      );
    })}
    <td className="px-2 py-1 text-right font-semibold tabular-nums" style={shade(r.total, CAP.total)}>{formatPercent(r.total)}</td>
  </tr>
));
Row.displayName = 'Row';

/** Stock × period grid from each stock's tracking day; a real table, so it is its own data fallback. */
export const RangeGrid: React.FC<{ data: HeatmapResponse }> = ({ data }) => {
  const grain = (data.grain ?? 'week') as Grain;
  return (
    <div className="overflow-x-auto border border-hairline rounded-interactive">
      <table className="text-xs border-collapse" aria-label={`Move per ${grain} since each stock's tracking day`}>
        <thead>
          <tr className="text-subtle">
            <th className="sticky left-0 z-10 bg-paper text-left px-2 py-1.5">Stock · since</th>
            {data.columns.map((c) => <th key={c.key} className="px-1.5 py-1.5 font-medium whitespace-nowrap" title={c.key}>{colLabel(c.last_date, grain)}</th>)}
            <th className="px-2 py-1.5">Total</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r) => <Row key={r.symbol} r={r} cols={data.columns} grain={grain} />)}
        </tbody>
      </table>
    </div>
  );
};
