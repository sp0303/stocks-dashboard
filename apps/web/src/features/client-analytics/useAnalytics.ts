import { useQuery } from '@tanstack/react-query';
import {
  NotComputedError,
  fetchAnalyticsPerformance,
  fetchAnalyticsSummary,
  fetchClientCorporateActions,
  fetchPlaybook,
  fetchTradeAnalytics,
  type Pool,
} from '@/lib/apiAnalytics';

/** Server state lives in TanStack Query only (LLD-frontend §5.4). A 404 is not retried. */
const retry = (count: number, err: unknown) => !(err instanceof NotComputedError) && count < 2;
const staleTime = 60_000;

export const useAnalyticsSummary = (clientId: string) =>
  useQuery({ queryKey: ['analytics', clientId, 'summary'], queryFn: () => fetchAnalyticsSummary(clientId), retry, staleTime });

export const useAnalyticsPerformance = (clientId: string) =>
  useQuery({ queryKey: ['analytics', clientId, 'performance'], queryFn: () => fetchAnalyticsPerformance(clientId), retry, staleTime });

export const useTradeAnalytics = (clientId: string, pool: Pool) =>
  useQuery({ queryKey: ['analytics', clientId, 'trades', pool], queryFn: () => fetchTradeAnalytics(clientId, pool), retry, staleTime });

export const usePlaybook = (clientId: string, pool: Pool) =>
  useQuery({ queryKey: ['analytics', clientId, 'playbook', pool], queryFn: () => fetchPlaybook(clientId, pool), retry, staleTime });

export const useClientCorporateActions = (clientId: string) =>
  useQuery({ queryKey: ['analytics', clientId, 'corporate-actions'], queryFn: () => fetchClientCorporateActions(clientId), retry, staleTime });
