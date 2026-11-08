import React from 'react';
import { CalendarClock, Gauge } from 'lucide-react';
import { formatPercent } from '@/lib/api';
import type { ScreenerSnapshot } from '@/lib/apiResearch';
import { StaleScreenAlert } from './StaleScreenAlert';

interface Props {
  snap: ScreenerSnapshot;
}

const REGIME_CLS: Record<string, string> = {
  on: 'border-positive/40 bg-positive/5',
  caution: 'border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950/30',
  off: 'border-negative/40 bg-negative/5',
};
const REGIME_LABEL: Record<string, string> = { on: 'Risk on', caution: 'Caution', off: 'Risk off' };

/** v1 market context: regime (with reasons), F&O expiry phase, events window, and a stale warning. */
export const MarketContextBanner: React.FC<Props> = ({ snap }) => {
  const reg = snap.market?.regime;
  const exp = snap.market?.expiry;
  const ev = snap.market?.events_window;
  const asOf = snap.data_as_of ?? snap.as_of;
  return (
    <div className="space-y-2">
      {snap.is_stale && <StaleScreenAlert asOf={asOf} sessionsBehind={snap.sessions_behind} />}
      {(reg || exp) && (
        <div className={`flex flex-wrap items-center gap-x-5 gap-y-1 p-3 text-xs rounded-interactive border ${REGIME_CLS[reg?.state ?? ''] ?? 'border-hairline bg-paper'}`}>
          {reg && (
            <span className="flex items-center gap-1.5 text-ink" title={snap.market?.regime_basis ?? undefined}>
              <Gauge className="w-4 h-4" aria-hidden />
              <strong>Regime: {REGIME_LABEL[reg.state] ?? reg.state}</strong>
              {reg.size_multiplier != null && <span className="text-subtle">· size ×{reg.size_multiplier}</span>}
              {reg.breadth != null && <span className="text-subtle">· breadth {formatPercent(reg.breadth, 0)}</span>}
              {reg.vix != null && <span className="text-subtle">· VIX {reg.vix.toFixed(1)}</span>}
            </span>
          )}
          {exp && exp.next_expiry && (
            <span className="flex items-center gap-1.5 text-ink" title={exp.calendar ?? undefined}>
              <CalendarClock className="w-4 h-4" aria-hidden />
              F&amp;O expiry {exp.next_expiry}
              {exp.sessions_to_expiry != null && <span className="text-subtle">· {exp.sessions_to_expiry} sessions · {exp.phase}</span>}
              {exp.in_entry_window && <strong className="text-ink">· entry window</strong>}
            </span>
          )}
          {ev && <span className="text-subtle">{ev.stocks_with_events} stocks with results/ex-dates to {ev.to}</span>}
          {reg?.reasons && reg.reasons.length > 0 && <span className="w-full text-subtle">{reg.reasons.join(' · ')}</span>}
        </div>
      )}
    </div>
  );
};
