import React from 'react';
import { ArrowDownLeft, ArrowUpRight, Trash2 } from 'lucide-react';
import { formatRupees, type TradeItem } from '@/lib/api';
import { isBuy } from '@/lib/apiLedger';
import { SymbolWithExchange } from '@/components/ExchangeBadge';

interface Props {
  trade: TradeItem;
  canDelete: boolean;
  busy: boolean;
  onDelete: (t: TradeItem) => void;
}

export const TradeRow: React.FC<Props> = React.memo(({ trade: t, canDelete, busy, onDelete }) => {
  const buy = isBuy(t.trade_type);
  return (
    <tr className="hover:bg-canvas/50 transition-colors">
      <td className="py-3 px-4 text-xs font-mono text-subtle">{t.trade_date}</td>
      <td className="py-3 px-4 text-xs font-bold text-ink">
        <SymbolWithExchange symbol={t.symbol} exchange={t.exchange} />
      </td>
      <td className="py-3 px-4 text-xs font-semibold">
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] ${buy ? 'bg-positive/10 text-positive' : 'bg-negative/10 text-negative'}`}>
          {buy ? <ArrowUpRight className="w-3 h-3" aria-hidden /> : <ArrowDownLeft className="w-3 h-3" aria-hidden />}
          {buy ? 'BUY' : 'SELL'}
        </span>
      </td>
      <td className="py-3 px-4 text-right font-mono text-xs text-ink">{t.quantity.toLocaleString('en-IN')}</td>
      <td className="py-3 px-4 text-right font-mono text-xs text-ink">{formatRupees(t.price)}</td>
      <td className="py-3 px-4 text-right font-mono text-xs font-semibold text-ink">{formatRupees(t.trade_value)}</td>
      <td className="py-3 px-4 text-[11px] uppercase text-subtle">{t.source}</td>
      <td className="py-3 px-4 text-xs font-mono text-subtle truncate max-w-[120px]">
        {t.broker_trade_id || t.broker_order_id || '—'}
      </td>
      <td className="py-3 px-4 text-right">
        {canDelete && t.source === 'manual' && (
          <button
            type="button"
            onClick={() => onDelete(t)}
            disabled={busy}
            aria-label={`Delete manual ${t.symbol} trade of ${t.trade_date}`}
            className="p-1 rounded-interactive text-subtle hover:text-negative disabled:opacity-50"
          >
            <Trash2 className="w-3.5 h-3.5" aria-hidden />
          </button>
        )}
      </td>
    </tr>
  );
});
TradeRow.displayName = 'TradeRow';
