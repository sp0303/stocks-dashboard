import React from 'react';
import { formatPercent, formatRupees } from '@/lib/api';
import type { ClosedTrade } from '@/lib/apiAdmin';

const NUM = 'py-2.5 px-3 text-right font-mono text-xs';

export const ClosedTradeRow: React.FC<{ r: ClosedTrade }> = React.memo(({ r }) => {
  const tone = r.pnl < 0 ? 'text-negative' : 'text-positive';
  return (
    <tr>
      <td className="py-2.5 px-3 text-xs text-ink">{r.client_name}</td>
      <td className="py-2.5 px-3 text-xs font-semibold text-ink">{r.symbol}</td>
      <td className={NUM}>{r.quantity.toLocaleString('en-IN')}</td>
      <td className={NUM}>{formatRupees(r.buy_price)}</td>
      <td className={NUM}>{formatRupees(r.sell_price)}</td>
      <td className={NUM}>{r.buy_date}</td>
      <td className={NUM}>{r.sell_date}</td>
      <td className={NUM}>{r.days}</td>
      <td className={`${NUM} ${tone}`}>{formatRupees(r.pnl)}</td>
      <td className={`${NUM} ${tone}`}>{formatPercent(r.pnl_pct)}</td>
    </tr>
  );
});
ClosedTradeRow.displayName = 'ClosedTradeRow';
