import React from 'react';

/** Small labelled stat tile. tone 'neg' only for negative numbers (ember rule). */
export const Stat: React.FC<{ label: string; value: string; hint?: string; tone?: 'pos' | 'neg' }> = ({ label, value, hint, tone }) => (
  <div className="bg-canvas border border-hairline rounded-interactive p-3" title={hint}>
    <div className="text-[11px] font-semibold text-subtle uppercase">{label}</div>
    <div className={`text-sm font-bold mt-0.5 ${tone === 'neg' ? 'text-negative' : tone === 'pos' ? 'text-positive' : 'text-ink'}`}>{value}</div>
    {hint && <div className="text-[10px] text-subtle mt-0.5">{hint}</div>}
  </div>
);

export const toneOf = (v: number | null | undefined): 'pos' | 'neg' | undefined =>
  v == null ? undefined : v < 0 ? 'neg' : v > 0 ? 'pos' : undefined;
