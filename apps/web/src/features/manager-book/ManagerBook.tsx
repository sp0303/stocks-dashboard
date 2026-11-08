import React from 'react';
import { EmptyBlock } from '@/components/QueryStates';
import { BookView } from './BookView';
import { useBookManagerId } from './useBook';

interface ManagerBookProps {
  onSelectClient: (clientId: string) => void;
}

/** Manager book page: composition only (AGENTS §5.3). */
export const ManagerBook: React.FC<ManagerBookProps> = ({ onSelectClient }) => {
  const managerId = useBookManagerId();
  if (!managerId) {
    return <EmptyBlock title="No manager selected" hint="As super-admin, open a manager's book from the admin page (View book)." />;
  }
  return <BookView managerId={managerId} onSelectClient={onSelectClient} />;
};
