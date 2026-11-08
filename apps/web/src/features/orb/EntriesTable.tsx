import React from 'react';
import { formatRupees } from '@/lib/api';
import type { OrbEntry } from './api';

export const EntriesTable: React.FC<{ entries: OrbEntry[] }> = ({ entries }) => {
  if (entries.length === 0) {
    return <p className="text-subtle text-sm">No entry signals on this day.</p>;
  }
  return (
    <table className="w-full text-xs" aria-label="Entry signals">
      <thead className="text-subtle text-left">
        <tr><th className="py-1">Time</th><th>Symbol</th><th>Side</th><th>Entry</th><th>Stop</th><th>T1</th><th>T2</th><th>Qty</th></tr>
      </thead>
      <tbody>
        {entries.map((e) => (
          <tr key={`${e.sym}-${e.time}`} className="border-t border-hairline">
            <td className="py-1">{e.time}</td>
            <td className="font-semibold">{e.sym}</td>
            <td>{e.side ?? '—'}</td>
            <td>{formatRupees(e.entry)}</td>
            <td>{formatRupees(e.stop)}</td>
            <td>{formatRupees(e.t1)}</td>
            <td>{formatRupees(e.t2)}</td>
            <td>{e.qty ?? '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
};
