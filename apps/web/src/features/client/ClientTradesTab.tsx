import React, { useCallback, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Search } from 'lucide-react';
import { fetchTrades, formatRupees, type TradeItem } from '@/lib/api';
import { voidManualTrade } from '@/lib/apiLedger';
import { useAuthStore } from '@/stores/authStore';
import { ManualTradeForm } from '@/features/ledger';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryStates';
import { TradeRow } from './TradeRow';

interface ClientTradesTabProps {
  clientId: string;
}

const HEADERS = ['Date', 'Symbol', 'Side', 'Qty', 'Price', 'Trade Value', 'Source', 'Broker Ref', ''];
const RIGHT = new Set(['Qty', 'Price', 'Trade Value']);

export const ClientTradesTab: React.FC<ClientTradesTabProps> = ({ clientId }) => {
  const token = useAuthStore((s) => s.accessToken);
  const role = useAuthStore((s) => s.role);
  const canEdit = role !== 'client';
  const qc = useQueryClient();
  const [symbol, setSymbol] = useState('');
  const [side, setSide] = useState<string>('');
  const [adding, setAdding] = useState(false);

  const { data: trades, isLoading, error, refetch } = useQuery<TradeItem[]>({
    queryKey: ['clientTrades', clientId, symbol, side, token],
    queryFn: () => fetchTrades({ clientId, symbol: symbol.trim() || undefined, side: side || undefined, limit: 200 }, token),
  });

  const remove = useMutation({
    mutationFn: (id: number) => voidManualTrade(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clientTrades', clientId] });
      qc.invalidateQueries({ queryKey: ['client', clientId] });
    },
  });

  const voidTrade = remove.mutate;
  const onDelete = useCallback(
    (t: TradeItem) => {
      const msg = `Delete manual trade ${t.trade_type.toUpperCase()} ${t.quantity} ${t.symbol} @ ${formatRupees(t.price)} on ${t.trade_date}?\nIt is voided (kept in the ledger for audit) and the portfolio is recomputed.`;
      if (window.confirm(msg)) voidTrade(t.trade_id);
    },
    [voidTrade]
  );

  return (
    <div className="bg-paper border border-hairline rounded-card overflow-hidden shadow-sm">
      <div className="p-5 border-b border-hairline flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-4 h-4 text-subtle absolute left-2.5 top-1/2 -translate-y-1/2" aria-hidden />
            <input
              type="text"
              aria-label="Filter by symbol"
              placeholder="Filter by symbol..."
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              className="pl-8 pr-3 py-1.5 text-xs bg-canvas border border-hairline rounded-xl text-ink focus:outline-none focus:ring-1 focus:ring-ink"
            />
          </div>
          <select aria-label="Filter by side" value={side} onChange={(e) => setSide(e.target.value)} className="px-2.5 py-1.5 text-xs bg-canvas border border-hairline rounded-xl text-ink focus:outline-none">
            <option value="">All Sides</option>
            <option value="buy">BUY</option>
            <option value="sell">SELL</option>
          </select>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-subtle">{trades?.length ?? 0} Trades</span>
          {canEdit && (
            <button type="button" onClick={() => setAdding((v) => !v)} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-interactive border border-hairline bg-paper text-xs font-semibold text-ink hover:bg-canvas">
              <Plus className="w-3.5 h-3.5" aria-hidden /> {adding ? 'Close' : 'Manual trade'}
            </button>
          )}
        </div>
      </div>

      {adding && canEdit && <ManualTradeForm clientId={clientId} onDone={() => setAdding(false)} />}
      {remove.error && <ErrorBlock message={(remove.error as Error).message} />}
      {isLoading && <LoadingBlock rows={4} label="Loading trades" />}
      {!isLoading && error && <ErrorBlock message="Failed to load trades." onRetry={() => refetch()} />}
      {!isLoading && !error && trades?.length === 0 && <EmptyBlock title="No trades recorded for this client." />}
      {!isLoading && !error && trades && trades.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm" aria-label="Trade history">
            <thead>
              <tr className="bg-canvas/60 text-subtle text-xs border-b border-hairline">
                {HEADERS.map((h, i) => (
                  <th key={i} className={`py-3 px-4 font-semibold ${RIGHT.has(h) ? 'text-right' : ''}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {trades.map((t) => (
                <TradeRow key={t.trade_id} trade={t} canDelete={canEdit} busy={remove.isPending} onDelete={onDelete} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
