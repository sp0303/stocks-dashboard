import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { createManualTrade, type ManualTradeCreate } from '@/lib/apiLedger';

interface Props {
  clientId: string;
  onDone: () => void;
}

const inputCls = 'px-2.5 py-1.5 text-xs bg-canvas border border-hairline rounded-interactive text-ink focus:outline-none focus:ring-1 focus:ring-ink';
const labelCls = 'flex flex-col gap-1 text-[11px] text-subtle font-semibold';

function newKey(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID().replace(/-/g, '')
    : `${Date.now()}${Math.random().toString(36).slice(2)}`;
}

/** Manual trade entry (source='manual'). One idempotency key per form instance prevents double-submits. */
export const ManualTradeForm: React.FC<Props> = ({ clientId, onDone }) => {
  const qc = useQueryClient();
  const [key] = useState(newKey);
  const [f, setF] = useState({ symbol: '', exchange: 'NSE', trade_date: '', trade_type: 'buy', quantity: '', price: '', note: '' });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setF((prev) => ({ ...prev, [k]: k === 'symbol' ? e.target.value.toUpperCase() : e.target.value }));

  const mutation = useMutation({
    mutationFn: () => {
      const body: ManualTradeCreate = {
        client_id: clientId,
        symbol: f.symbol.trim(),
        exchange: f.exchange as 'NSE' | 'BSE',
        trade_date: f.trade_date,
        trade_type: f.trade_type as 'buy' | 'sell',
        quantity: Number(f.quantity),
        price: Number(f.price),
        note: f.note.trim() || null,
        idempotency_key: key,
      };
      return createManualTrade(body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clientTrades', clientId] });
      qc.invalidateQueries({ queryKey: ['client', clientId] });
      onDone();
    },
  });

  const valid = f.symbol.trim() !== '' && f.trade_date !== '' && Number(f.quantity) > 0 && f.price !== '' && Number(f.price) >= 0;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (valid && !mutation.isPending) mutation.mutate();
  };

  return (
    <form onSubmit={submit} className="p-4 border-b border-hairline bg-canvas/40 flex flex-wrap items-end gap-2" aria-label="Add manual trade">
      <label className={labelCls}>Symbol<input className={`${inputCls} w-28`} value={f.symbol} onChange={set('symbol')} required /></label>
      <label className={labelCls}>Exchange
        <select className={inputCls} value={f.exchange} onChange={set('exchange')}><option>NSE</option><option>BSE</option></select>
      </label>
      <label className={labelCls}>Date<input type="date" className={inputCls} value={f.trade_date} onChange={set('trade_date')} required /></label>
      <label className={labelCls}>Side
        <select className={inputCls} value={f.trade_type} onChange={set('trade_type')}>
          <option value="buy">Buy</option><option value="sell">Sell</option>
        </select>
      </label>
      <label className={labelCls}>Qty<input type="number" min="0" step="any" className={`${inputCls} w-24`} value={f.quantity} onChange={set('quantity')} required /></label>
      <label className={labelCls}>Price ₹<input type="number" min="0" step="0.0001" className={`${inputCls} w-28`} value={f.price} onChange={set('price')} required /></label>
      <label className={`${labelCls} flex-1 min-w-[140px]`}>Note<input className={inputCls} value={f.note} onChange={set('note')} maxLength={500} /></label>
      <button type="submit" disabled={!valid || mutation.isPending} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-interactive bg-ink text-paper text-xs font-semibold disabled:opacity-50">
        <Plus className="w-3.5 h-3.5" aria-hidden /> {mutation.isPending ? 'Saving…' : 'Add trade'}
      </button>
      {mutation.error && <span role="alert" className="text-xs text-negative w-full">{(mutation.error as Error).message}</span>}
    </form>
  );
};
