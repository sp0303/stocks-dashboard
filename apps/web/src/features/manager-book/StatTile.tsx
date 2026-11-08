import React from 'react';

interface Props {
  label: string;
  value: string;
  sub?: string;
  tone?: 'up' | 'down' | 'neutral';
  title?: string;
}

/** Compact KPI tile (v1 "Stat"). Tone is paired with a text cue, never colour alone. */
export const StatTile: React.FC<Props> = ({ label, value, sub, tone = 'neutral', title }) => {
  const toneClass = tone === 'up' ? 'text-positive' : tone === 'down' ? 'text-negative' : 'text-ink';
  return (
    <div className="bg-paper border border-hairline rounded-card p-4" title={title}>
      <div className="text-[11px] font-semibold text-subtle uppercase tracking-wider">{label}</div>
      <div className={`mt-1 text-lg font-bold font-mono truncate ${toneClass}`}>{value}</div>
      {sub && <div className="text-xs text-subtle mt-0.5 truncate">{sub}</div>}
    </div>
  );
};
