import { formatRate, formatRupees } from '@/lib/api';
import type { Highlight } from '@/lib/apiAnalytics';

const LABEL: Record<Highlight['kind'], string> = {
  best_open: 'Best open holding',
  worst_open: 'Weakest open holding',
  longest_held: 'Longest held',
  best_closed: 'Best closed trade',
  worst_closed: 'Worst closed trade',
  win_rate: 'Win rate',
};

function valueText(h: Highlight): string {
  if (h.value == null) return '—';
  if (h.unit === 'ratio') return formatRate(h.value, 1);
  if (h.unit === 'inr') return formatRupees(h.value, 0);
  return `${Math.round(h.value)} days`;
}

/** Deterministic sentence for one highlight (no LLM; numbers via the shared formatters, R12). */
export function highlightText(h: Highlight): { label: string; text: string } {
  const v = valueText(h);
  const text =
    h.kind === 'win_rate'
      ? `${v} of closed delivery trades were profitable`
      : `${h.symbol} · ${v}${h.unit === 'ratio' ? ` ${h.basis}` : ''}`;
  return { label: LABEL[h.kind], text };
}
