/** Chart colours read from the design tokens (DESIGN.md: no raw hex), so light and dark both work. */
export interface ChartTokens {
  ink: string;
  subtle: string;
  hairline: string;
  accent: string;
  positive: string;
  negative: string;
  paper: string;
}

function cssVar(name: string): string {
  if (typeof window === 'undefined') return 'currentColor';
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || 'currentColor';
}

export function chartTokens(): ChartTokens {
  return {
    ink: cssVar('--ink'),
    subtle: cssVar('--subtle'),
    hairline: cssVar('--hairline'),
    accent: cssVar('--accent'),
    positive: cssVar('--positive'),
    negative: cssVar('--negative'),
    paper: cssVar('--paper'),
  };
}

/** Shared axis styling. */
export function axisStyle(t: ChartTokens) {
  return {
    axisLine: { lineStyle: { color: t.hairline } },
    axisLabel: { color: t.subtle, fontSize: 11 },
    splitLine: { lineStyle: { color: t.hairline } },
  };
}
