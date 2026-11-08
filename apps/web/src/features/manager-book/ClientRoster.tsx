import React from 'react';
import { UserPlus, Users } from 'lucide-react';
import type { BookRosterItem } from '@/lib/apiAdmin';
import { EmptyBlock } from '@/components/QueryStates';
import { RosterRow, type RosterAction } from './RosterRow';

const HEAD = ['Client', 'Broker · code', 'Capital deployed', 'Current invested', 'Market value', 'Total P&L', 'Return', 'Trades', ''];

interface Props {
  clients: BookRosterItem[];
  onAdd: () => void;
  onAction: (a: RosterAction, c: BookRosterItem) => void;
}

export const ClientRoster: React.FC<Props> = ({ clients, onAdd, onAction }) => (
  <div className="bg-paper border border-hairline rounded-card overflow-hidden shadow-sm">
    <div className="p-5 border-b border-hairline flex items-center justify-between">
      <h2 className="text-base font-semibold text-ink flex items-center gap-2">
        <Users className="w-5 h-5 text-subtle" aria-hidden /> Client portfolios ({clients.length})
      </h2>
      <button type="button" onClick={onAdd} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-interactive bg-ink text-paper text-xs font-semibold">
        <UserPlus className="w-4 h-4" aria-hidden /> Add client
      </button>
    </div>
    {clients.length === 0 ? (
      <EmptyBlock title="No clients in this book yet" hint="Add a client, then upload a tradebook for them." />
    ) : (
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-sm" aria-label="Client portfolios">
          <thead>
            <tr className="bg-canvas/60 text-subtle text-xs border-b border-hairline">
              {HEAD.map((h, i) => (
                <th key={h || 'actions'} className={`py-3 px-4 font-semibold ${i > 1 ? 'text-right' : ''}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {clients.map((c) => (
              <RosterRow key={c.client_id} c={c} onAction={onAction} />
            ))}
          </tbody>
        </table>
      </div>
    )}
  </div>
);
