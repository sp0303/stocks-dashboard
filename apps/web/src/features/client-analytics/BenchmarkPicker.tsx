import React from 'react';
import type { BenchmarkTrack } from '@/lib/apiAnalytics';

interface Props {
  benchmarks: BenchmarkTrack[];
  value: string;
  onChange: (code: string) => void;
}

export const BenchmarkPicker: React.FC<Props> = ({ benchmarks, value, onChange }) => (
  <label className="inline-flex items-center gap-2 text-xs text-subtle">
    Benchmark
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="px-3 py-1.5 rounded-interactive border border-hairline bg-paper text-ink text-xs font-semibold"
    >
      {benchmarks.map((b) => (
        <option key={b.code} value={b.code}>
          {b.label}{b.is_tri ? ' (TRI)' : ''}{b.stale ? ' — stale' : ''}
        </option>
      ))}
    </select>
  </label>
);
