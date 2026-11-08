import React from 'react';
import { formatPercent, type ClientMetrics } from '@/lib/api';

interface Props {
  metrics: ClientMetrics;
}

const Tile: React.FC<{ label: string; value: string; hint?: string; tone?: 'neg' }> = ({ label, value, hint, tone }) => (
  <div className="bg-paper border border-hairline rounded-interactive p-3 text-center" title={hint}>
    <div className="text-[11px] font-semibold text-subtle uppercase">{label}</div>
    <div className={`text-sm font-bold mt-0.5 ${tone === 'neg' ? 'text-negative' : 'text-ink'}`}>{value}</div>
    {hint && <div className="text-[10px] text-subtle mt-0.5">{hint}</div>}
  </div>
);

/**
 * Risk row. R12: 0 is a value (checks use != null). R4: XIRR is money-weighted and the engine
 * returns null under one year or on non-convergence — we say so instead of showing a number.
 */
export const ClientRiskStats: React.FC<Props> = ({ metrics: m }) => (
  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
    <Tile label="Volatility" value={m.annualized_volatility != null ? formatPercent(m.annualized_volatility) : '—'} />
    <Tile label="Sharpe Ratio" value={m.sharpe_ratio != null ? m.sharpe_ratio.toFixed(2) : '—'} />
    <Tile
      label="Max Drawdown"
      value={m.max_drawdown != null ? formatPercent(m.max_drawdown) : '—'}
      tone={m.max_drawdown != null && m.max_drawdown < 0 ? 'neg' : undefined}
    />
    <Tile
      label="XIRR (money-weighted)"
      value={m.xirr != null ? formatPercent(m.xirr) : '—'}
      hint={m.xirr != null ? 'Annualised, cash-flow weighted' : 'Not shown: under 1 year of history or did not converge'}
      tone={m.xirr != null && m.xirr < 0 ? 'neg' : undefined}
    />
  </div>
);
