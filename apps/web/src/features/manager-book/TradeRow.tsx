import React from 'react';
import { formatRupees, type TradeItem } from '@/lib/api';

const NUM = 'py-2.5 px-3 text-right font-mono text-xs text-ink';

export const TradeRow: React.FC<{ t: TradeItem }> = React.memo(({ t }) => {
  const buy = t.trade_type === 'BUY';
  return (
    <tr>
      <td className="py-2.5 px-3 text-xs font-mono text-subtle">{t.trade_date}</td>
      <td className="py-2.5 px-3 text-xs text-ink">{t.client_name || t.client_code || t.client_id.slice(0, 8)}</td>
      <td className="py-2.5 px-3 text-xs font-semibold text-ink">
        {t.symbol} <span className="text-[10px] text-subtle">{t.exchange} · {t.segment}</span>
      </td>
      <td className={`py-2.5 px-3 text-xs font-semibold ${buy ? 'text-positive' : 'text-negative'}`}>{t.trade_type}</td>
      <td className={NUM}>{t.quantity.toLocaleString('en-IN')}</td>
      <td className={NUM}>{formatRupees(t.price)}</td>
      <td className={NUM}>{formatRupees(t.trade_value)}</td>
      {/* R15: unknown charges are null, shown as "—", never 0 */}
      <td className={NUM}>{t.charges_known ? formatRupees(t.charges) : '—'}</td>
      <td className="py-2.5 px-3 text-xs text-subtle">{t.source}</td>
    </tr>
  );
});
TradeRow.displayName = 'TradeRow';
