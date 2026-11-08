import React, { useMemo, useState } from 'react';
import { formatRupees } from '@/lib/api';
import { ClosedTradeRow } from './ClosedTradeRow';
import { Pager } from './Pager';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryStates';
import { SORTS, viewClosedTrades, type SortId } from './closedTrades';
import { useClosedTrades, useUrlParam } from './useBook';

const PAGE = 50;
const COLS = ['Account', 'Stock', 'Qty', 'Buy', 'Sell', 'Bought', 'Sold', 'Days', 'P&L', 'P&L %'];
const FIELD = 'px-2.5 py-1.5 text-xs bg-canvas border border-hairline rounded-interactive text-ink';

/** Closed-trade journal across every account (v1 ManagerTradeLog). */
export const ClosedTradesTable: React.FC<{ managerId: string }> = ({ managerId }) => {
  const q = useClosedTrades(managerId);
  const [account, setAccount] = useUrlParam('tla');
  const [symbol, setSymbol] = useUrlParam('tls');
  const [sort, setSort] = useUrlParam('tlo', 'recent');
  const [page, setPage] = useState(0);
  const accounts = useMemo(() => {
    const m = new Map((q.data ?? []).map((r) => [r.client_id, r.client_name]));
    return [...m.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [q.data]);
  const view = useMemo(() => viewClosedTrades(q.data ?? [], account, symbol, sort as SortId), [q.data, account, symbol, sort]);

  if (q.isLoading) return <LoadingBlock rows={6} label="Loading closed trades" />;
  if (q.isError) return <ErrorBlock message="Could not load closed trades." onRetry={() => q.refetch()} />;
  if (!q.data?.length) return <EmptyBlock title="No closed trades yet across any client" hint="Closed round trips appear once the portfolio worker has matched sells to buys." />;
  const total = view.reduce((s, r) => s + r.pnl, 0);
  const rows = view.slice(page * PAGE, page * PAGE + PAGE);
  const pages = Math.ceil(view.length / PAGE);
  return (
    <div>
      <div className="p-4 flex flex-wrap items-center gap-2 border-b border-hairline">
        <select aria-label="Account" value={account} onChange={(e) => { setAccount(e.target.value); setPage(0); }} className={FIELD}>
          <option value="">All accounts</option>
          {accounts.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
        </select>
        <input aria-label="Symbol" placeholder="Symbol…" value={symbol} onChange={(e) => { setSymbol(e.target.value.toUpperCase()); setPage(0); }} className={FIELD} />
        <select aria-label="Sort" value={sort} onChange={(e) => setSort(e.target.value)} className={FIELD}>
          {Object.entries(SORTS).map(([id, s]) => <option key={id} value={id}>{s.label}</option>)}
        </select>
        <span className="ml-auto text-xs text-subtle">
          {view.length} trades · P&L <span className={total < 0 ? 'text-negative' : 'text-positive'}>{formatRupees(total, 0)}</span>
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm" aria-label="Closed trades">
          <thead>
            <tr className="bg-canvas/60 text-subtle text-xs">{COLS.map((c, i) => <th key={c} className={`py-2.5 px-3 font-semibold ${i > 1 ? 'text-right' : ''}`}>{c}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {rows.map((r) => (
              <ClosedTradeRow key={`${r.client_id}:${r.symbol}:${r.buy_date}:${r.sell_date}:${r.quantity}`} r={r} />
            ))}
          </tbody>
        </table>
      </div>
      <Pager page={page} pages={pages} onPage={setPage} />
    </div>
  );
};
