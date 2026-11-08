import React, { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { createBookClient, deleteBookClient, updateBookClient, type BookRosterItem } from '@/lib/apiAdmin';
import { ConfirmDialog } from '@/features/super-admin';
import { ClientRoster } from './ClientRoster';
import { ClientFormModal } from './ClientFormModal';
import type { RosterAction } from './RosterRow';

interface Props {
  managerId: string;
  clients: BookRosterItem[];
  onSelectClient: (id: string) => void;
}

type Pending = { kind: 'add' } | { kind: 'edit' | 'delete'; c: BookRosterItem } | null;

/** Roster with add / edit / soft-delete. Invalidates the book and the client lists on change. */
export const ClientsTab: React.FC<Props> = ({ managerId, clients, onSelectClient }) => {
  const qc = useQueryClient();
  const [pending, setPending] = useState<Pending>(null);
  const done = () => {
    qc.invalidateQueries({ queryKey: ['book'] });
    qc.invalidateQueries({ queryKey: ['clients'] });
    qc.invalidateQueries({ queryKey: ['admin'] });
  };
  const onAction = (a: RosterAction, c: BookRosterItem) => (a === 'open' ? onSelectClient(c.client_id) : setPending({ kind: a, c }));
  const close = () => setPending(null);

  return (
    <>
      <ClientRoster clients={clients} onAdd={() => setPending({ kind: 'add' })} onAction={onAction} />
      {pending?.kind === 'add' && (
        <ClientFormModal managerId={managerId} onClose={close} onSubmit={(d) => createBookClient(managerId, d).then(done)} />
      )}
      {pending?.kind === 'edit' && (
        <ClientFormModal managerId={managerId} client={pending.c} onClose={close} onSubmit={(d) => updateBookClient(pending.c.client_id, d).then(done)} />
      )}
      {pending?.kind === 'delete' && (
        <ConfirmDialog
          title={`Delete ${pending.c.name}?`}
          message="The client is removed from the book and their login disabled. Trades and uploads are kept (soft delete)."
          confirmLabel="Delete client"
          destructive
          onConfirm={() => deleteBookClient(pending.c.client_id).then(done)}
          onClose={close}
        />
      )}
    </>
  );
};
