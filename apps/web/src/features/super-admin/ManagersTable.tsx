import React from 'react';
import { Building2 } from 'lucide-react';
import type { ManagerItem } from '@/lib/api';
import { EmptyBlock } from '@/components/QueryStates';
import { ManagerRow, type ManagerAction } from './ManagerRow';

interface Props {
  managers: ManagerItem[];
  onAction: (action: ManagerAction, m: ManagerItem) => void;
}

export const ManagersTable: React.FC<Props> = ({ managers, onAction }) => (
  <div className="bg-paper border border-hairline rounded-card overflow-hidden shadow-sm">
    <div className="p-5 border-b border-hairline flex items-center justify-between">
      <h2 className="text-base font-semibold text-ink flex items-center gap-2">
        <Building2 className="w-5 h-5 text-subtle" aria-hidden /> Investment managers
      </h2>
      <span className="text-xs text-subtle">{managers.length} registered</span>
    </div>
    {managers.length === 0 ? (
      <EmptyBlock title="No managers yet" hint="Use “Add manager” to create the first desk." />
    ) : (
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-sm" aria-label="Investment managers">
          <thead>
            <tr className="bg-canvas/60 text-subtle text-xs border-b border-hairline">
              <th className="py-3 px-4 font-semibold">Manager</th>
              <th className="py-3 px-4 font-semibold">Firm / desk</th>
              <th className="py-3 px-4 font-semibold">Email</th>
              <th className="py-3 px-4 font-semibold text-right">Active clients</th>
              <th className="py-3 px-4 font-semibold text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {managers.map((m) => (
              <ManagerRow key={m.manager_id} m={m} onAction={onAction} />
            ))}
          </tbody>
        </table>
      </div>
    )}
  </div>
);
