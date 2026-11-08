import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { fetchManagerMetrics } from '@/lib/api';
import {
  fetchBookPerformance,
  fetchBookSummary,
  fetchClientReturns,
  fetchClosedTrades,
} from '@/lib/apiAdmin';
import { useAuthStore } from '@/stores/authStore';

/** Manager whose book is shown: the impersonated one for a super-admin, else the caller's. */
export function useBookManagerId(): string | null {
  const managerId = useAuthStore((s) => s.managerId);
  const impersonated = useAuthStore((s) => s.impersonatedManagerId);
  return impersonated || managerId;
}

export const bookKey = (mid: string, part: string) => ['book', mid, part] as const;

export const useBookSummary = (mid: string) =>
  useQuery({ queryKey: bookKey(mid, 'summary'), queryFn: () => fetchBookSummary(mid) });

export const useBookPerformance = (mid: string) =>
  useQuery({ queryKey: bookKey(mid, 'performance'), queryFn: () => fetchBookPerformance(mid) });

export const useClientReturns = (mid: string) =>
  useQuery({ queryKey: bookKey(mid, 'client-returns'), queryFn: () => fetchClientReturns(mid) });

export const useClosedTrades = (mid: string) =>
  useQuery({ queryKey: bookKey(mid, 'closed-trades'), queryFn: () => fetchClosedTrades(mid) });

/** Book risk metrics (volatility / Sharpe / drawdown) from the portfolio module. */
export const useBookRisk = (mid: string) =>
  useQuery({ queryKey: ['managerMetrics', mid], queryFn: () => fetchManagerMetrics(mid) });

/** A single URL search param as state (AGENTS §5.5: filters and tabs live in the URL). */
export function useUrlParam(name: string, fallback = ''): [string, (v: string) => void] {
  const [params, setParams] = useSearchParams();
  const value = params.get(name) ?? fallback;
  const set = (v: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (v && v !== fallback) next.set(name, v);
        else next.delete(name);
        return next;
      },
      { replace: true },
    );
  return [value, set];
}
