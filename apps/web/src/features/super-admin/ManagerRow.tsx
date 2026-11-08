import React from 'react';
import { ArrowUpRight, Pencil, Power, Trash2 } from 'lucide-react';
import type { ManagerItem } from '@/lib/api';

export type ManagerAction = 'edit' | 'toggle' | 'delete' | 'view';

interface Props {
  m: ManagerItem;
  onAction: (action: ManagerAction, m: ManagerItem) => void;
}

const BTN = 'p-1.5 rounded-interactive text-subtle hover:text-ink hover:bg-canvas transition-colors';

export const ManagerRow: React.FC<Props> = React.memo(({ m, onAction }) => (
  <tr className="hover:bg-canvas/50 transition-colors">
    <td className="py-3 px-4 font-medium text-ink">
      {m.name}
      {!m.is_active && (
        <span className="ml-2 text-[11px] px-2 py-0.5 rounded-full border border-hairline text-subtle">Inactive</span>
      )}
    </td>
    <td className="py-3 px-4 text-subtle text-xs">{m.firm || '—'}</td>
    <td className="py-3 px-4 text-subtle text-xs font-mono">{m.email}</td>
    <td className="py-3 px-4 text-right text-ink font-mono text-xs font-semibold">{m.client_count}</td>
    <td className="py-3 px-4">
      <div className="flex justify-end gap-1">
        <button type="button" className={BTN} title="Edit" aria-label={`Edit ${m.name}`} onClick={() => onAction('edit', m)}>
          <Pencil className="w-4 h-4" />
        </button>
        <button
          type="button"
          className={BTN}
          title={m.is_active ? 'Deactivate' : 'Reactivate'}
          aria-label={`${m.is_active ? 'Deactivate' : 'Reactivate'} ${m.name}`}
          onClick={() => onAction('toggle', m)}
        >
          <Power className="w-4 h-4" />
        </button>
        <button type="button" className={`${BTN} hover:text-negative`} title="Delete" aria-label={`Delete ${m.name}`} onClick={() => onAction('delete', m)}>
          <Trash2 className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => onAction('view', m)}
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-interactive text-xs font-semibold bg-canvas border border-hairline hover:bg-paper text-ink"
        >
          View book <ArrowUpRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </td>
  </tr>
));
ManagerRow.displayName = 'ManagerRow';
