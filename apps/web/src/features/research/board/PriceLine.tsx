import React from 'react';
import { formatPercent, formatRupees } from '@/lib/api';

interface Props {
  price: number | null | undefined;
  asOf?: string | null;
  /** The close is more than one session old (R6): shown, but flagged. */
  stale?: boolean;
  /** Decimal change to show next to the price (vs entry or vs cost). */
  change?: number | null;
  changeLabel?: string;
  amount?: number | null;
}

/** Price with its as-of date (R6) and a signed change; "unpriced" is shown as text, not as cost. */
export const PriceLine: React.FC<Props> = ({ price, asOf, stale, change, changeLabel, amount }) => {
  if (price == null) {
    return <div className="text-[11px] text-subtle italic">Unpriced — no close stored</div>;
  }
  const up = change != null && change >= 0;
  return (
    <div className="space-y-0.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-sm text-ink">{formatRupees(price)}</span>
        {asOf && (
          <span className={`text-[10px] ${stale ? 'text-amber-600 dark:text-amber-400 font-semibold' : 'text-subtle'}`}>
            {stale ? 'stale · ' : ''}close {asOf}
          </span>
        )}
      </div>
      {change != null && (
        <div className={`font-mono text-[11px] ${up ? 'text-positive' : 'text-ember'}`}>
          {up ? '▲' : '▼'} {formatPercent(change)}
          {amount != null && <> · {formatRupees(amount)}</>}
          {changeLabel && <span className="text-subtle"> {changeLabel}</span>}
        </div>
      )}
    </div>
  );
};
