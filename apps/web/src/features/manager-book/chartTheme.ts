/** Resolve design tokens (CSS variables) to concrete colours for ECharts, which cannot read var(). */
export function token(name: string): string {
  if (typeof window === 'undefined') return '';
  return getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim();
}

export function axisStyle() {
  const subtle = token('subtle');
  const hairline = token('hairline');
  return {
    axisLabel: { color: subtle, fontSize: 11 },
    axisLine: { lineStyle: { color: hairline } },
    splitLine: { lineStyle: { color: hairline } },
  };
}
