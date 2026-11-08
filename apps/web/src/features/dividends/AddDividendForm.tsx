import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { createDividend } from '@/lib/apiLedger';

interface Props {
  clientId: string;
  onDone: () => void;
}

const inputCls = 'px-2.5 py-1.5 text-xs bg-canvas border border-hairline rounded-interactive text-ink focus:outline-none focus:ring-1 focus:ring-ink';

export const AddDividendForm: React.FC<Props> = ({ clientId, onDone }) => {
  const qc = useQueryClient();
  const [symbol, setSymbol] = useState('');
  const [exDate, setExDate] = useState('');
  const [perShare, setPerShare] = useState('');
  const [qty, setQty] = useState('');

  const mutation = useMutation({
    mutationFn: () =>
      createDividend({
        client_id: clientId,
        symbol: symbol.trim().toUpperCase(),
        ex_date: exDate,
        amount_per_share: Number(perShare),
        quantity: Number(qty),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dividends', clientId] });
      onDone();
    },
  });

  const valid = symbol.trim() !== '' && exDate !== '' && Number(perShare) > 0 && Number(qty) > 0;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (valid && !mutation.isPending) mutation.mutate();
  };

  return (
    <form onSubmit={submit} className="p-4 border-b border-hairline bg-canvas/40 flex flex-wrap items-end gap-2" aria-label="Add dividend">
      <label className="flex flex-col gap-1 text-[11px] text-subtle font-semibold">
        Symbol
        <input className={inputCls} value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} placeholder="ITC" required />
      </label>
      <label className="flex flex-col gap-1 text-[11px] text-subtle font-semibold">
        Ex-date
        <input type="date" className={inputCls} value={exDate} onChange={(e) => setExDate(e.target.value)} required />
      </label>
      <label className="flex flex-col gap-1 text-[11px] text-subtle font-semibold">
        ₹ per share
        <input type="number" step="0.0001" min="0" className={`${inputCls} w-28`} value={perShare} onChange={(e) => setPerShare(e.target.value)} required />
      </label>
      <label className="flex flex-col gap-1 text-[11px] text-subtle font-semibold">
        Shares held
        <input type="number" step="any" min="0" className={`${inputCls} w-28`} value={qty} onChange={(e) => setQty(e.target.value)} required />
      </label>
      <button
        type="submit"
        disabled={!valid || mutation.isPending}
        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-interactive bg-ink text-paper text-xs font-semibold disabled:opacity-50"
      >
        <Plus className="w-3.5 h-3.5" aria-hidden /> {mutation.isPending ? 'Saving…' : 'Add dividend'}
      </button>
      {mutation.error && <span role="alert" className="text-xs text-negative w-full">{(mutation.error as Error).message}</span>}
    </form>
  );
};
