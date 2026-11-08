/** Client analytics feature: import only through this file (feature-sliced boundaries). */
import { lazy } from 'react';

export { AnalyticsTabPanel, isAnalyticsTab, type AnalyticsTabKey } from './AnalyticsTabPanel';
export const OverviewExtras = lazy(() => import('./OverviewExtras'));
