import React from 'react';
import { formatPercent } from '@/lib/api';
import { StatTile } from './StatTile';
import { useBookRisk } from './useBook';

const REASON = 'not computed yet for this book';

/** Volatility / Sharpe / max drawdown when the API returns them; "—" with the reason otherwise. */
export const BookRiskTiles: React.FC<{ managerId: string }> = ({ managerId }) => {
  const q = useBookRisk(managerId);
  const m = q.data;
  const why = q.isLoading ? 'loading…' : q.isError ? 'could not load metrics' : REASON;
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" aria-label="Book risk metrics">
      <StatTile
        label="Volatility (ann.)"
        value={m?.weighted_volatility != null ? formatPercent(m.weighted_volatility) : '—'}
        sub={m?.weighted_volatility != null ? 'time-weighted daily NAV' : why}
      />
      <StatTile
        label="Sharpe"
        value={m?.weighted_sharpe != null ? m.weighted_sharpe.toFixed(2) : '—'}
        sub={m?.weighted_sharpe != null ? 'daily excess returns' : why}
      />
      <StatTile
        label="Max drawdown"
        value={m?.max_drawdown != null ? formatPercent(m.max_drawdown) : '—'}
        tone={m?.max_drawdown != null && m.max_drawdown < 0 ? 'down' : 'neutral'}
        sub={m?.max_drawdown != null ? 'peak to trough' : why}
      />
    </div>
  );
};
