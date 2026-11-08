import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { formatRupees, type PositionItem } from '@/lib/api';

/** R6.4: holdings with no usable price are excluded from BOTH cost and value — say which. */
export const UnpricedNotice: React.FC<{ positions: PositionItem[] }> = ({ positions }) => {
  const unpriced = positions.filter((p) => p.priced === false);
  if (unpriced.length === 0) return null;
  const cost = unpriced.reduce((s, p) => s + p.invested, 0);
  const names = unpriced.map((p) => `${p.symbol} (${p.exchange})`).join(', ');
  return (
    <div role="status" className="mx-5 mt-4 p-3 flex items-start gap-2 text-xs text-ink border border-hairline bg-canvas rounded-interactive">
      <AlertTriangle className="w-4 h-4 shrink-0 text-subtle" aria-hidden />
      <span>
        No live price for <strong>{names}</strong> — excluded from Market Value and Current Invested
        ({formatRupees(cost)} at cost) until a price is available.
      </span>
    </div>
  );
};
