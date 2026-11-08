import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchCorporateActions, type CorporateActionItem } from '@/lib/api';
import { Calendar, Search, Tag } from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';

export const CorporateActionsTable: React.FC = () => {
  const token = useAuthStore((s) => s.accessToken);
  const [symbol, setSymbol] = useState('');
  const [actionType, setActionType] = useState('');

  const { data: actions, isLoading, error } = useQuery<CorporateActionItem[]>({
    queryKey: ['corporateActions', symbol, actionType, token],
    queryFn: () =>
      fetchCorporateActions(
        {
          symbol: symbol.trim() || undefined,
          type: actionType || undefined,
          limit: 100,
        },
        token
      ),
  });

  return (
    <div className="bg-paper border border-hairline rounded-card overflow-hidden shadow-sm">
      <div className="p-5 border-b border-hairline flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-4 h-4 text-subtle absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search symbol..."
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              className="pl-8 pr-3 py-1.5 text-xs bg-canvas border border-hairline rounded-xl text-ink focus:outline-none focus:ring-1 focus:ring-ink"
            />
          </div>
          <select
            value={actionType}
            onChange={(e) => setActionType(e.target.value)}
            className="px-2.5 py-1.5 text-xs bg-canvas border border-hairline rounded-xl text-ink focus:outline-none"
          >
            <option value="">All Action Types</option>
            <option value="SPLIT">SPLIT</option>
            <option value="BONUS">BONUS</option>
            <option value="DIVIDEND">DIVIDEND</option>
            <option value="DEMERGER">DEMERGER</option>
            <option value="RIGHTS">RIGHTS</option>
            <option value="BUYBACK">BUYBACK</option>
          </select>
        </div>
        <span className="text-xs text-subtle">{actions?.length || 0} Events Listed</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-sm">
          <thead>
            <tr className="bg-canvas/60 text-subtle text-xs border-b border-hairline">
              <th className="py-3 px-4 font-semibold">Ex-Date</th>
              <th className="py-3 px-4 font-semibold">Symbol</th>
              <th className="py-3 px-4 font-semibold">Type</th>
              <th className="py-3 px-4 font-semibold text-right">Ratio / Amount</th>
              <th className="py-3 px-4 font-semibold">Subject / Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {isLoading && (
              <tr>
                <td colSpan={5} className="py-8 text-center text-subtle text-xs animate-pulse">
                  Loading corporate actions...
                </td>
              </tr>
            )}
            {error && (
              <tr>
                <td colSpan={5} className="py-8 text-center text-negative text-xs">
                  Failed to load corporate actions.
                </td>
              </tr>
            )}
            {!isLoading && !error && actions && actions.length === 0 && (
              <tr>
                <td colSpan={5} className="py-8 text-center text-subtle text-xs">
                  No corporate actions found.
                </td>
              </tr>
            )}
            {actions?.map((ca) => (
              <tr key={ca.action_id} className="hover:bg-canvas/50 transition-colors">
                <td className="py-3 px-4 text-xs font-mono text-subtle flex items-center gap-1.5">
                  <Calendar className="w-3.5 h-3.5 text-subtle" />
                  {ca.ex_date}
                </td>
                <td className="py-3 px-4 text-xs font-bold text-ink">{ca.symbol}</td>
                <td className="py-3 px-4 text-xs">
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-canvas text-ink border border-hairline">
                    <Tag className="w-3 h-3 text-subtle" />
                    {ca.type}
                  </span>
                </td>
                <td className="py-3 px-4 text-right font-mono text-xs text-ink font-semibold">
                  {ca.qty_multiplier ? `×${ca.qty_multiplier}` : ca.amount_per_share ? `₹${ca.amount_per_share}` : '—'}
                </td>
                <td className="py-3 px-4 text-xs text-subtle max-w-md truncate" title={ca.subject || ''}>
                  {ca.subject || '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
