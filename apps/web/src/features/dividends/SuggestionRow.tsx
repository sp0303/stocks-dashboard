import React from 'react';
import { Check } from 'lucide-react';
import { formatRupees } from '@/lib/api';
import type { DividendSuggestion } from '@/lib/apiLedger';

interface Props {
  s: DividendSuggestion;
  busy: boolean;
  onAccept: (s: DividendSuggestion) => void;
}

export const SuggestionRow: React.FC<Props> = React.memo(({ s, busy, onAccept }) => (
  <tr>
    <td className="py-2 px-3 font-semibold text-ink" title={s.subject ?? undefined}>{s.symbol}</td>
    <td className="py-2 px-3 text-subtle">{s.ex_date}</td>
    <td className="py-2 px-3 text-right font-mono">{formatRupees(s.amount_per_share)}</td>
    <td className="py-2 px-3 text-right font-mono">{s.estimated_quantity}</td>
    <td className="py-2 px-3 text-right font-mono text-ink">{formatRupees(s.estimated_total)}</td>
    <td className="py-2 px-3 text-right">
      <button
        type="button"
        disabled={busy}
        onClick={() => onAccept(s)}
        aria-label={`Accept ${s.symbol} dividend of ${formatRupees(s.estimated_total)}`}
        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-interactive border border-hairline bg-paper text-ink font-semibold hover:bg-canvas disabled:opacity-50"
      >
        <Check className="w-3 h-3" aria-hidden /> Accept
      </button>
    </td>
  </tr>
));
SuggestionRow.displayName = 'SuggestionRow';
