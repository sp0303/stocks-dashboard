import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Activity } from 'lucide-react';
import { fetchBenchmarkHealth, type BenchmarkHealth } from '@/lib/apiResearch';

/**
 * Header pill: latest market-data date (from benchmark health, R10). Stale benchmarks alarm
 * with text as well as colour (colour is never the only signal).
 */
export const DataFreshnessPill: React.FC = () => {
  const { data, isLoading, error } = useQuery<BenchmarkHealth[]>({
    queryKey: ['market', 'benchmarkHealth'],
    queryFn: fetchBenchmarkHealth,
    staleTime: 5 * 60_000,
    refetchInterval: 5 * 60_000,
  });

  const dates = (data ?? []).map((b) => b.last_date).filter((d): d is string => !!d).sort();
  const latest = dates.length ? dates[dates.length - 1] : null;
  const stale = (data ?? []).filter((b) => b.is_alarm);

  let label = 'Market data …';
  let dot = 'bg-subtle';
  let title = 'Checking market data freshness';
  if (!isLoading && (error || !latest)) {
    label = 'Market data: unknown';
    title = error ? (error as Error).message : 'No benchmark data available';
  } else if (latest) {
    label = stale.length ? `Data ${latest} · stale` : `Data ${latest}`;
    dot = stale.length ? 'bg-negative' : 'bg-positive';
    title = stale.length
      ? `Stale: ${stale.map((b) => `${b.code} (${b.sessions_behind} sessions behind)`).join(', ')}`
      : 'Benchmarks up to date';
  }

  return (
    <div
      className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-canvas border border-hairline"
      title={title}
      role="status"
      aria-label={`${label}. ${title}`}
    >
      <Activity className="w-3.5 h-3.5 text-subtle" aria-hidden />
      <span className={`w-1.5 h-1.5 rounded-full ${dot}`} aria-hidden />
      <span className="text-ink">{label}</span>
    </div>
  );
};
