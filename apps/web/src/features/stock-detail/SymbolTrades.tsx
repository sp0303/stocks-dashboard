import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchTrades, formatRupees, type TradeItem } from '@/lib/api';
import { isBuy } from '@/lib/apiLedger';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryStates';

interface Props {
  clientId: string;
  symbol: string;
}

/** The client's trades in one symbol, newest first. */
export const SymbolTrades: React.FC<Props> = ({ clientId, symbol }) => {
  const { data, isLoading, error, refetch } = useQuery<TradeItem[]>({
    queryKey: ['clientTrades', clientId, 'symbol', symbol],
    queryFn: () => fetchTrades({ clientId, symbol, limit: 500 }),
  });

  if (isLoading) return <LoadingBlock rows={3} label="Loading trades" />;
  if (error) return <ErrorBlock message="Failed to load trades." onRetry={() => refetch()} />;
  if (!data || data.length === 0) return <EmptyBlock title={`No trades in ${symbol}.`} />;

  return (
    <table className="w-full text-left text-xs" aria-label={`${symbol} trades`}>
      <thead>
        <tr className="text-subtle border-b border-hairline">
          <th className="py-2 pr-2 font-semibold">Date</th>
          <th className="py-2 pr-2 font-semibold">Side</th>
          <th className="py-2 pr-2 font-semibold text-right">Qty</th>
          <th className="py-2 pr-2 font-semibold text-right">Price</th>
          <th className="py-2 font-semibold text-right">Value</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-hairline">
        {data.map((t) => {
          const buy = isBuy(t.trade_type);
          return (
            <tr key={t.trade_id}>
              <td className="py-2 pr-2 font-mono text-subtle">{t.trade_date}</td>
              <td className={`py-2 pr-2 font-semibold ${buy ? 'text-positive' : 'text-negative'}`}>
                {buy ? 'BUY' : 'SELL'}
                {t.source === 'manual' && <span className="ml-1 text-[10px] text-subtle font-normal">(manual)</span>}
              </td>
              <td className="py-2 pr-2 text-right font-mono">{t.quantity.toLocaleString('en-IN')}</td>
              <td className="py-2 pr-2 text-right font-mono">{formatRupees(t.price)}</td>
              <td className="py-2 text-right font-mono">{formatRupees(t.trade_value)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
};
