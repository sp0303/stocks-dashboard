/**
 * Holdings heatmap (modules/heatmap). Returns are decimals (R12); `null` = no close, never 0.
 * Mirrors pi_api.modules.heatmap.schemas.
 */
import { fetchWithAuth } from '@/lib/api';

export type HeatmapMode = 'day' | 'range';
export type HeatmapGrain = 'auto' | 'day' | 'week' | 'month';

interface Held {
  symbol: string;
  exchange: string | null;
  qty: number;
  invested: number;
  clients: number;
  entry_date: string | null;
  suspect: boolean;
}
export interface HeatmapTile extends Held {
  ret: number | null;
  close: number | null;
  prev_close: number | null;
  prev_date: string | null;
}
export interface HeatmapRow extends Held {
  start: string | null;
  cells: Record<string, number>;
  total: number | null;
}
export interface HeatmapResponse {
  mode: HeatmapMode;
  day: string | null;
  latest: string | null;
  end: string | null;
  grain: Exclude<HeatmapGrain, 'auto'> | null;
  tiles: HeatmapTile[];
  columns: { key: string; last_date: string }[];
  rows: HeatmapRow[];
  no_history: string[];
}

export interface HeatmapQuery {
  mode: HeatmapMode;
  clientIds: string[];
  day?: string;
  start?: string;
  grain?: HeatmapGrain;
}

export async function fetchHeatmap(managerId: string, q: HeatmapQuery): Promise<HeatmapResponse> {
  const p = new URLSearchParams({ mode: q.mode });
  if (q.clientIds.length) p.set('client_ids', q.clientIds.join(','));
  if (q.mode === 'day' && q.day) p.set('day', q.day);
  if (q.mode === 'range') {
    if (q.start) p.set('start', q.start);
    p.set('grain', q.grain ?? 'auto');
  }
  const res = await fetchWithAuth(`/api/v1/portfolio/managers/${managerId}/heatmap?${p}`);
  if (!res.ok) throw new Error(`Failed to load heatmap: ${res.statusText}`);
  return res.json();
}
