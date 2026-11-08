import React, { useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { fetchTrades } from '@/lib/api';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryStates';
import { Pager } from './Pager';
import { TradeRow } from './TradeRow';
import { useBookSummary, useUrlParam } from './useBook';

const PAGE = 100;
const FIELD = 'px-2.5 py-1.5 text-xs bg-canvas border border-hairline rounded-interactive text-ink';
const COLS = ['Date', 'Account', 'Symbol', 'Side', 'Qty', 'Price', 'Value', 'Charges', 'Source'];

/** Every stored trade across the book's accounts, server-filtered and paged. */
export const AllTradesTable: React.FC<{ managerId: string }> = ({ managerId }) => {
  const roster = useBookSummary(managerId);
  const [client, setClient] = useUrlParam('tc');
  const [symbol, setSymbol] = useUrlParam('ts');
  const [side, setSide] = useUrlParam('tside');
  const [from, setFrom] = useUrlParam('tfrom');
  const [to, setTo] = useUrlParam('tto');
  const [page, setPage] = useState(0);
  const params = { clientId: client || undefined, managerId, symbol: symbol.trim() || undefined, side: side || undefined, startDate: from || undefined, endDate: to || undefined, limit: PAGE + 1, offset: page * PAGE };
  const q = useQuery({ queryKey: ['book', managerId, 'trades', params], queryFn: () => fetchTrades(params), placeholderData: keepPreviousData });
  const reset = <T,>(fn: (v: T) => void) => (v: T) => { fn(v); setPage(0); };
  const rows = (q.data ?? []).slice(0, PAGE);
  const more = (q.data?.length ?? 0) > PAGE;

  return (
    <div>
      <div className="p-4 flex flex-wrap items-center gap-2 border-b border-hairline">
        <select aria-label="Account" value={client} onChange={(e) => reset(setClient)(e.target.value)} className={FIELD}>
          <option value="">All accounts</option>
          {(roster.data?.clients ?? []).map((c) => <option key={c.client_id} value={c.client_id}>{c.name}</option>)}
        </select>
        <input aria-label="Symbol" placeholder="Symbol…" value={symbol} onChange={(e) => reset(setSymbol)(e.target.value.toUpperCase())} className={FIELD} />
        <select aria-label="Side" value={side} onChange={(e) => reset(setSide)(e.target.value)} className={FIELD}>
          <option value="">Buy and sell</option>
          <option value="BUY">Buy</option>
          <option value="SELL">Sell</option>
        </select>
        <input aria-label="From date" type="date" value={from} onChange={(e) => reset(setFrom)(e.target.value)} className={FIELD} />
        <input aria-label="To date" type="date" value={to} onChange={(e) => reset(setTo)(e.target.value)} className={FIELD} />
      </div>
      {q.isLoading && <LoadingBlock rows={6} label="Loading trades" />}
      {q.isError && <ErrorBlock message="Could not load trades." onRetry={() => q.refetch()} />}
      {q.data && rows.length === 0 && <EmptyBlock title="No trades match these filters" />}
      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm" aria-label="All trades">
            <thead>
              <tr className="bg-canvas/60 text-subtle text-xs">{COLS.map((c, i) => <th key={c} className={`py-2.5 px-3 font-semibold ${i > 3 && i < 8 ? 'text-right' : ''}`}>{c}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-hairline">{rows.map((t) => <TradeRow key={t.trade_id} t={t} />)}</tbody>
          </table>
        </div>
      )}
      <Pager page={page} pages={more ? page + 2 : page + 1} onPage={setPage} />
    </div>
  );
};
