import React from 'react';
import { CalendarClock } from 'lucide-react';
import { formatRupees } from '@/lib/api';
import type { ClientCorporateAction } from '@/lib/apiAnalytics';
import { AnalyticsGate } from './AnalyticsGate';
import { Card } from './Card';
import { useClientCorporateActions } from './useAnalytics';

function detail(a: ClientCorporateAction): string {
  if (a.qty_multiplier != null) return `Quantity ×${a.qty_multiplier}`;
  if (a.amount_per_share != null) return `${formatRupees(a.amount_per_share)} per share`;
  return a.subject ?? '—';
}

/** R8: split/bonus are applied by the engine; demerger/merger/rights/buyback are flagged for review. */
const ClientCorporateActionsTab: React.FC<{ clientId: string }> = ({ clientId }) => {
  const q = useClientCorporateActions(clientId);
  const rows = q.data ?? [];
  return (
    <Card title="Corporate actions on this client's stocks" icon={<CalendarClock className="w-5 h-5 text-subtle" aria-hidden />}>
      <AnalyticsGate isLoading={q.isLoading} error={q.error} onRetry={() => q.refetch()} empty={rows.length === 0} emptyTitle="No corporate actions since the first trade">
        <div className="overflow-auto max-h-[32rem]">
          <table className="w-full text-sm" aria-label="Client corporate actions">
            <thead className="text-[11px] uppercase text-subtle sticky top-0 bg-paper">
              <tr>
                {['Ex-date', 'Stock', 'Type', 'Detail', 'Status'].map((c) => (
                  <th key={c} scope="col" className="text-left py-2 pr-3">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.action_id} className="border-t border-hairline">
                  <td className="py-1.5 pr-3 text-subtle">{a.ex_date}</td>
                  <td className="py-1.5 pr-3 font-semibold text-ink">{a.symbol}</td>
                  <td className="py-1.5 pr-3 text-ink">{a.type}</td>
                  <td className="py-1.5 pr-3 text-ink">{detail(a)}</td>
                  <td className={`py-1.5 text-xs ${a.needs_review ? 'text-negative font-semibold' : 'text-subtle'}`}>
                    {a.needs_review ? '⚠ Needs review' : a.applied_by_engine ? 'Applied to quantities' : 'Info'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </AnalyticsGate>
    </Card>
  );
};

export default ClientCorporateActionsTab;
