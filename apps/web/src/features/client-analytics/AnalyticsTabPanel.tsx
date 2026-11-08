import React, { Suspense, lazy } from 'react';
import { LoadingBlock } from '@/components/QueryStates';

export type AnalyticsTabKey = 'allocation' | 'performance' | 'trade-analytics' | 'playbook' | 'corporate-actions' | 'watchlist';

const TABS: Record<AnalyticsTabKey, React.LazyExoticComponent<React.FC<{ clientId: string }>>> = {
  allocation: lazy(() => import('./AllocationTab')),
  performance: lazy(() => import('./PerformanceTab')),
  'trade-analytics': lazy(() => import('./TradeAnalyticsTab')),
  playbook: lazy(() => import('./PlaybookTab')),
  'corporate-actions': lazy(() => import('./ClientCorporateActionsTab')),
  watchlist: lazy(() => import('./ClientWatchlistTab')),
};

export const isAnalyticsTab = (k: string): k is AnalyticsTabKey => k in TABS;

/** Renders one lazily loaded analytics tab (each tab is its own chunk, LLD-frontend §5.6). */
export const AnalyticsTabPanel: React.FC<{ tab: AnalyticsTabKey; clientId: string }> = ({ tab, clientId }) => {
  const Tab = TABS[tab];
  return (
    <Suspense fallback={<LoadingBlock rows={3} label="Loading tab" />}>
      <Tab clientId={clientId} />
    </Suspense>
  );
};
