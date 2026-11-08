import React from 'react';
import { formatPercent, formatRate, formatRupees } from '@/lib/api';
import type { AnalyticsSummary } from '@/lib/apiAnalytics';
import { Stat, toneOf } from './Stat';

/** Beta & alpha vs Nifty 50 (R12: 0 is a value) and the intraday pool (R9: P&L only, no "invested"). */
export const SensitivityStats: React.FC<{ s: AnalyticsSummary }> = ({ s }) => {
  const vs = s.beta_benchmark ? `vs ${s.beta_benchmark}` : 'no benchmark data';
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <Stat label="Beta" value={s.beta != null ? s.beta.toFixed(2) : '—'} hint={vs} />
      <Stat label="Alpha (Jensen)" value={formatPercent(s.alpha)} hint={`annualised ${vs}`} tone={toneOf(s.alpha)} />
      <Stat
        label="Intraday P&L"
        value={formatRupees(s.intraday.net_pnl, 0)}
        hint={`${s.intraday.trades} same-day trades · win ${formatRate(s.intraday.win_rate, 0)} · not in Total P&L`}
        tone={toneOf(s.intraday.net_pnl)}
      />
      <Stat
        label="Excluded"
        value={`${s.unmatched_sells} unmatched sells`}
        hint={`${s.derivative_trades} F&O trades (never capital)`}
      />
    </div>
  );
};
