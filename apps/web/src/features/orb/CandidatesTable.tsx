import React from 'react';
import { formatPercent, formatRupees } from '@/lib/api';
import type { OrbScreenRow } from './api';

/** Lists over 50 rows must be virtualised (AGENTS §5.7); the screen is capped at 50 instead. */
const MAX_ROWS = 50;

export const CandidatesTable: React.FC<{ rows: OrbScreenRow[] }> = ({ rows }) => {
  const shown = rows.slice(0, MAX_ROWS);
  return (
    <div className="space-y-1">
      <table className="w-full text-xs" aria-label="Screened candidates">
        <thead className="text-subtle text-left">
          <tr><th className="py-1">Symbol</th><th>Result</th><th>OR high</th><th>OR low</th><th>OR width</th><th>RVOL</th><th>Turnover (cr)</th></tr>
        </thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.sym} className="border-t border-hairline">
              <td className="py-1 font-semibold">{r.sym}</td>
              <td className={r.passed ? 'text-positive' : 'text-subtle'}>{r.passed ? 'passed' : 'filtered'}</td>
              <td>{formatRupees(r.or_high)}</td>
              <td>{formatRupees(r.or_low)}</td>
              <td>{formatPercent(r.or_width, 2).replace('+', '')}</td>
              <td>{r.rvol != null ? `${r.rvol.toFixed(2)}×` : '—'}</td>
              <td>{r.turnover_cr != null ? r.turnover_cr.toFixed(2) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > MAX_ROWS && (
        <p className="text-subtle text-xs">Showing {MAX_ROWS} of {rows.length} candidates (passed first, then by RVOL).</p>
      )}
    </div>
  );
};
