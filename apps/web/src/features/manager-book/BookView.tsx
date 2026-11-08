import React, { Suspense, lazy } from 'react';
import { ErrorBlock, LoadingBlock } from '@/components/QueryStates';
import { BookTiles } from './BookTiles';
import { BookTabs, TABS, type BookTab } from './BookTabs';
import { ClientsTab } from './ClientsTab';
import { useBookSummary, useUrlParam } from './useBook';

const ManagerMetricsTab = lazy(() => import('./ManagerMetricsTab').then((m) => ({ default: m.ManagerMetricsTab })));
const ManagerHoldingsTable = lazy(() => import('./ManagerHoldingsTable').then((m) => ({ default: m.ManagerHoldingsTable })));
const ManagerTradeLog = lazy(() => import('./ManagerTradeLog').then((m) => ({ default: m.ManagerTradeLog })));
const CorporateActionsTable = lazy(() => import('./CorporateActionsTable').then((m) => ({ default: m.CorporateActionsTable })));

interface Props {
  managerId: string;
  onSelectClient: (clientId: string) => void;
}

/** Tiles + tabs for one manager's book; tab state lives in the URL (`book`). */
export const BookView: React.FC<Props> = ({ managerId, onSelectClient }) => {
  const summary = useBookSummary(managerId);
  const [raw, setTab] = useUrlParam('book', 'clients');
  const tab: BookTab = raw in TABS ? (raw as BookTab) : 'clients';

  if (summary.isLoading) return <LoadingBlock rows={6} label="Loading manager book" />;
  if (summary.isError || !summary.data) return <ErrorBlock message="Could not load the manager book." onRetry={() => summary.refetch()} />;
  return (
    <div className="space-y-6">
      <BookTiles s={summary.data} />
      <BookTabs tab={tab} onTab={setTab} />
      {tab === 'clients' && <ClientsTab managerId={managerId} clients={summary.data.clients} onSelectClient={onSelectClient} />}
      <Suspense fallback={<LoadingBlock rows={6} label="Loading tab" />}>
        {tab === 'performance' && <ManagerMetricsTab managerId={managerId} />}
        {tab === 'holdings' && <ManagerHoldingsTable managerId={managerId} />}
        {tab === 'trades' && <ManagerTradeLog managerId={managerId} />}
        {tab === 'corporate-actions' && <CorporateActionsTable />}
      </Suspense>
    </div>
  );
};
