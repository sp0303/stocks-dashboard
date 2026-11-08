import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRightLeft, ShieldCheck, UserPlus } from 'lucide-react';
import { fetchClients, type ManagerItem } from '@/lib/api';
import { deleteManager, fetchManagers, updateManager } from '@/lib/apiAdmin';
import { ErrorBlock, LoadingBlock } from '@/components/QueryStates';
import { CreateManagerModal } from './CreateManagerModal';
import { ReassignClientModal } from './ReassignClientModal';
import { EditManagerModal } from './EditManagerModal';
import { ConfirmDialog } from './ConfirmDialog';
import { ManagersTable } from './ManagersTable';
import { PlatformTiles } from './PlatformTiles';
import { CorporateActionsPanel } from './CorporateActionsPanel';
import type { ManagerAction } from './ManagerRow';

interface Props {
  onImpersonateManager: (managerId: string, managerName: string) => void;
}

type Pending = { action: Exclude<ManagerAction, 'view'>; m: ManagerItem } | null;
const BTN = 'flex items-center gap-1.5 px-3.5 py-2 rounded-interactive text-xs font-semibold transition-colors';

export const SuperAdminDashboard: React.FC<Props> = ({ onImpersonateManager }) => {
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [reassigning, setReassigning] = useState(false);
  const [pending, setPending] = useState<Pending>(null);
  const managers = useQuery({ queryKey: ['admin', 'managers'], queryFn: fetchManagers });
  const clients = useQuery({ queryKey: ['clients'], queryFn: () => fetchClients() });
  const refresh = () => qc.invalidateQueries({ queryKey: ['admin'] });

  const onAction = (action: ManagerAction, m: ManagerItem) =>
    action === 'view' ? onImpersonateManager(m.manager_id, m.name) : setPending({ action, m });
  const close = () => setPending(null);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <h1 className="text-xl font-bold text-ink flex items-center gap-3">
          <ShieldCheck className="w-6 h-6 text-positive" aria-hidden /> Super-admin
        </h1>
        <div className="flex gap-2">
          <button type="button" onClick={() => setCreating(true)} className={`${BTN} bg-ink text-paper`}>
            <UserPlus className="w-4 h-4" aria-hidden /> Add manager
          </button>
          <button
            type="button"
            onClick={() => setReassigning(true)}
            disabled={!clients.data?.length || !managers.data?.length}
            className={`${BTN} border border-hairline bg-paper text-ink hover:bg-canvas disabled:opacity-40`}
          >
            <ArrowRightLeft className="w-4 h-4" aria-hidden /> Reassign client
          </button>
        </div>
      </div>
      <PlatformTiles />
      {managers.isLoading && <LoadingBlock rows={4} label="Loading managers" />}
      {managers.isError && <ErrorBlock message="Could not load managers." onRetry={() => managers.refetch()} />}
      {managers.data && <ManagersTable managers={managers.data} onAction={onAction} />}
      <CorporateActionsPanel />

      <CreateManagerModal isOpen={creating} onClose={() => setCreating(false)} onSuccess={refresh} />
      <ReassignClientModal
        isOpen={reassigning}
        onClose={() => setReassigning(false)}
        clients={clients.data || []}
        managers={(managers.data || []).filter((m) => m.is_active)}
        onSuccess={() => {
          refresh();
          qc.invalidateQueries({ queryKey: ['clients'] });
        }}
      />
      {pending?.action === 'edit' && <EditManagerModal manager={pending.m} onClose={close} onSaved={refresh} />}
      {pending?.action === 'toggle' && (
        <ConfirmDialog
          title={pending.m.is_active ? `Deactivate ${pending.m.name}?` : `Reactivate ${pending.m.name}?`}
          message={pending.m.is_active ? 'Their login is disabled; clients and history are kept.' : 'Their login is enabled again.'}
          confirmLabel={pending.m.is_active ? 'Deactivate' : 'Reactivate'}
          destructive={pending.m.is_active}
          onConfirm={() => updateManager(pending.m.manager_id, { is_active: !pending.m.is_active }).then(refresh)}
          onClose={close}
        />
      )}
      {pending?.action === 'delete' && (
        <ConfirmDialog
          title={`Delete ${pending.m.name}?`}
          message={
            pending.m.client_count > 0
              ? `${pending.m.name} still has ${pending.m.client_count} client(s). Reassign or delete them first.`
              : 'The manager is hidden and their login disabled. This is a soft delete; records are kept.'
          }
          confirmLabel="Delete manager"
          destructive
          onConfirm={() => deleteManager(pending.m.manager_id).then(refresh)}
          onClose={close}
        />
      )}
    </div>
  );
};
