/**
 * Client analytics API (GET /api/v1/analytics/clients/{id}/...). Precomputed by
 * portfolio-worker (pi_workers.analytics_compute). Ratios are decimals (R12).
 * Shapes mirror pi_core/analytics/client_report.py (the OpenAPI types the section
 * bodies as `Any`, so these are not generated).
 */
import { fetchWithAuth } from '@/lib/api';

const BASE = '/api/v1/analytics/clients';

export type Pool = 'delivery' | 'intraday';
export type AllocationBasis = 'current' | 'invested';
export type AllocationDim = 'sector' | 'cap' | 'asset' | 'stock';

export interface Section<T> {
  client_id: string;
  as_of: string;
  computed_at: string;
  engine_version: string;
  data: T;
}

export interface AllocationBucket { key: string; value: number; weight: number | null }
export interface Allocation {
  total: number;
  buckets: AllocationBucket[];
  unclassified: { count: number; value: number; weight: number | null; symbols: string[] };
}
export interface Concentration {
  holdings_count: number;
  top5_weight: number | null;
  top10_weight: number | null;
  herfindahl: number | null;
  largest_stock: { symbol: string; exchange: string; weight: number } | null;
  largest_sector: { key: string; weight: number | null } | null;
}
export interface Health {
  score: number;
  alerts: { code: string; message: string }[];
  missing: string[];
}
export interface Highlight {
  kind: 'best_open' | 'worst_open' | 'longest_held' | 'best_closed' | 'worst_closed' | 'win_rate';
  symbol: string | null;
  value: number | null;
  unit: 'ratio' | 'days' | 'inr';
  basis: string;
}
export interface ManualTrade {
  trade_id: number;
  trade_date: string;
  symbol: string;
  exchange: string;
  side: string;
  quantity: number;
  price: number;
  note: string | null;
}
export interface PoolSummary { trades: number; wins: number; win_rate: number | null; net_pnl: number }
export interface AnalyticsSummary {
  allocation: Record<AllocationBasis, Record<AllocationDim, Allocation>>;
  unpriced: { count: number; open_cost: number; symbols: string[] };
  concentration: Concentration;
  health: Health | null;
  beta_benchmark: string | null;
  beta: number | null;
  alpha: number | null;
  intraday: PoolSummary;
  derivative_trades: number;
  unmatched_sells: number;
  highlights: Highlight[];
  manual_trades: ManualTrade[];
}

export interface BucketRow { bucket: string; trades: number; wins: number; pnl: number; win_rate: number | null }
export interface TopTrade {
  symbol: string; exchange: string; sell_date: string; quantity: number;
  pnl: number; pnl_pct: number | null; holding_days: number;
}
export interface TradeAnalytics {
  closed_trades: number; winning_trades: number; losing_trades: number; breakeven_trades: number;
  win_rate: number | null; profit_factor: number | null; avg_win: number | null; avg_loss: number | null;
  payoff_ratio: number | null; expectancy: number | null; total_pnl: number; avg_holding_days: number | null;
  equity_curve: { date: string; cum_pnl: number; drawdown: number }[];
  distribution: BucketRow[]; monthly: BucketRow[]; by_weekday: BucketRow[]; by_holding: BucketRow[];
  top_winners: TopTrade[]; top_losers: TopTrade[];
}

export interface PlaybookRow {
  pool: Pool; symbol: string; exchange: string; trades: number; quantity: number;
  avg_buy_price: number | null; avg_sell_price: number | null; avg_days: number | null;
  pnl: number; pnl_pct: number | null; first_buy_date: string; last_sell_date: string; reason: string;
}

export interface BenchmarkTrack {
  code: string; label: string; is_tri: boolean; pnl: (number | null)[];
  last_index_date: string | null; sessions_behind: number; stale: boolean;
  index_return: number | null; start_backfilled: boolean;
}
export interface Performance {
  dates: string[]; net_invested: number[]; market_value: number[]; portfolio_pnl: number[];
  total_return: number | null; cagr: number | null; days: number; benchmarks: BenchmarkTrack[];
}

export interface ClientCorporateAction {
  action_id: number; symbol: string; ex_date: string; type: string;
  qty_multiplier: number | null; amount_per_share: number | null; subject: string | null;
  source: string; applied_by_engine: boolean; needs_review: boolean;
}

/** 404 = the worker has not computed this client yet: an empty state, not an error. */
export class NotComputedError extends Error {}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetchWithAuth(url);
  if (res.status === 404) throw new NotComputedError('Analytics not computed yet');
  if (!res.ok) throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  return res.json();
}

export const fetchAnalyticsSummary = (id: string) =>
  getJson<Section<AnalyticsSummary>>(`${BASE}/${id}/summary`);
export const fetchAnalyticsPerformance = (id: string) =>
  getJson<Section<Performance>>(`${BASE}/${id}/performance`);
export const fetchTradeAnalytics = (id: string, pool: Pool) =>
  getJson<Section<TradeAnalytics>>(`${BASE}/${id}/trades?pool=${pool}`);
export const fetchPlaybook = (id: string, pool: Pool) =>
  getJson<Section<PlaybookRow[]>>(`${BASE}/${id}/playbook?pool=${pool}`);
export const fetchClientCorporateActions = (id: string) =>
  getJson<ClientCorporateAction[]>(`${BASE}/${id}/corporate-actions`);

/** R14: authenticated fetch + blob, never a bare link. */
export async function exportPlaybookCsv(id: string): Promise<Blob> {
  const res = await fetchWithAuth(`${BASE}/${id}/playbook/export`);
  if (!res.ok) throw new Error(`Export failed: ${res.status} ${res.statusText}`);
  return res.blob();
}
