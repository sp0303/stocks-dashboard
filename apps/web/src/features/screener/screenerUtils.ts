import type { ScreenerRow } from '@/lib/apiResearch';

export type SortKey = 'score' | 'd1' | 'w1' | 'm1';
export const SORT_LABELS: Record<SortKey, string> = { score: 'Score', d1: '1D', w1: '1W', m1: '1M' };
export const TOP_N = [20, 50, 100] as const;

/** Desc by key; nulls last (R12: 0 is a real value, only null/undefined is missing). */
export function sortRows(rows: ScreenerRow[], key: SortKey): ScreenerRow[] {
  return [...rows].sort((a, b) => {
    const av = a[key];
    const bv = b[key];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    return bv - av;
  });
}

export function sectorsOf(rows: ScreenerRow[]): string[] {
  return Array.from(new Set(rows.map((r) => r.sector).filter((s): s is string => !!s))).sort();
}

export function sliceScreener(rows: ScreenerRow[], opts: { sector: string; sort: SortKey; top: number; q: string }): ScreenerRow[] {
  const q = opts.q.trim().toUpperCase();
  const filtered = rows.filter(
    (r) =>
      (!opts.sector || r.sector === opts.sector) &&
      (!q || r.symbol.includes(q) || (r.name ?? '').toUpperCase().includes(q))
  );
  return sortRows(filtered, opts.sort).slice(0, opts.top);
}

/** Setup label is shown only when the snapshot carries a real one. */
export function visibleSetup(setup: string | null | undefined): string | null {
  if (!setup) return null;
  const s = setup.trim();
  return s === '' || s.toLowerCase() === 'no setup' ? null : s;
}

export interface SectorSummary {
  sector: string;
  count: number;
  avgScore: number | null;
  avg: Record<'d1' | 'w1' | 'm1', number | null>;
  setups: number;
  leaders: ScreenerRow[];
}

function mean(vals: Array<number | null | undefined>): number | null {
  const xs = vals.filter((v): v is number => v != null);
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
}

export function summariseSectors(rows: ScreenerRow[]): SectorSummary[] {
  const groups = new Map<string, ScreenerRow[]>();
  for (const r of rows) {
    const k = r.sector || 'Unclassified';
    groups.set(k, [...(groups.get(k) ?? []), r]);
  }
  return Array.from(groups, ([sector, rs]) => ({
    sector,
    count: rs.length,
    avgScore: mean(rs.map((r) => r.score)),
    avg: { d1: mean(rs.map((r) => r.d1)), w1: mean(rs.map((r) => r.w1)), m1: mean(rs.map((r) => r.m1)) },
    setups: rs.filter((r) => visibleSetup(r.setup)).length,
    leaders: sortRows(rs, 'score').slice(0, 5),
  }));
}
