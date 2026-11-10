import type React from 'react';

/** Full colour at this move, per view (same caps as v1). */
export const CAP = { day: 0.05, week: 0.1, month: 0.2, total: 0.5 } as const;

/** Background tint for a decimal move. Tokens only (DESIGN.md); null = no data. */
export function shade(r: number | null | undefined, cap: number): React.CSSProperties {
  if (r == null) return { background: 'var(--canvas)', color: 'var(--subtle)' };
  const p = Math.round(Math.min(Math.abs(r) / cap, 1) * 80);
  if (p < 4) return { background: 'var(--canvas)', color: 'var(--ink)' };
  const hue = r > 0 ? 'var(--positive)' : 'var(--negative)';
  return { background: `color-mix(in srgb, ${hue} ${p}%, var(--paper))`, color: p > 50 ? 'var(--paper)' : 'var(--ink)' };
}

/** Column header for a period key, from the last trading date in it. */
export function colLabel(lastDate: string, grain: string): string {
  const d = new Date(`${lastDate}T00:00:00`);
  if (grain === 'month') return d.toLocaleDateString('en-IN', { month: 'short', year: '2-digit' });
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
}
