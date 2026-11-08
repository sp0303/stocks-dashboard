import { useCallback, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchScreenerLatest, type ScreenerSnapshot } from '@/lib/apiResearch';

export function useScreenerSnapshot() {
  return useQuery<ScreenerSnapshot>({
    queryKey: ['screener', 'latest'],
    queryFn: () => fetchScreenerLatest(),
    staleTime: 5 * 60_000,
  });
}

function readParam(name: string, fallback: string): string {
  try {
    return new URLSearchParams(window.location.search).get(name) ?? fallback;
  } catch {
    return fallback;
  }
}

/** Filter state mirrored into the URL query string (LLD-frontend: filters live in the URL). */
export function useUrlParam(name: string, fallback: string): [string, (v: string) => void] {
  const [value, setValue] = useState(() => readParam(name, fallback));
  const update = useCallback(
    (v: string) => {
      setValue(v);
      const url = new URL(window.location.href);
      if (v === fallback) url.searchParams.delete(name);
      else url.searchParams.set(name, v);
      window.history.replaceState(window.history.state, '', url.toString());
    },
    [name, fallback]
  );
  return [value, update];
}
