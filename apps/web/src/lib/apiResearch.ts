/**
 * Research + market read endpoints used by the stock drawer, screener and freshness pill.
 * Ratios returned by the API are decimals (Rule R12); format with formatPercent only.
 */
import { fetchWithAuth, type LatestClose } from '@/lib/api';

const API_BASE = '/api/v1';

export type Thesis = Record<string, unknown>;

export interface StockThesis {
  client_id: string;
  symbol: string;
  thesis: Thesis;
  updated_at: string;
}

export interface ScreenerRow {
  symbol: string;
  name?: string | null;
  sector?: string | null;
  setup?: string | null;
  typical_hold_days?: number | null;
  score?: number | null;
  rank?: number | null;
  value_score?: number | null;
  quality_score?: number | null;
  rsi?: number | null;
  rel_strength?: number | null;
  price?: number | null;
  d1?: number | null;
  w1?: number | null;
  m1?: number | null;
  y1?: number | null;
  from_52w_high?: number | null;
  events?: ScreenerEvent[];
}

/** Upcoming results / ex-dates for one stock (v1 event badges). */
export interface ScreenerEvent {
  kind: string;
  date: string;
  amount?: number | null;
}

export interface MarketRegime {
  state: 'on' | 'caution' | 'off' | string;
  size_multiplier?: number | null;
  reasons?: string[];
  breadth?: number | null;
  vix?: number | null;
}

export interface ExpiryPhase {
  next_expiry?: string | null;
  sessions_to_expiry?: number | null;
  phase?: string | null;
  in_entry_window?: boolean | null;
  calendar?: string | null;
}

export interface MarketContext {
  regime?: MarketRegime | null;
  expiry?: ExpiryPhase | null;
  regime_basis?: string | null;
  events_window?: { from: string; to: string; stocks_with_events: number } | null;
}

export interface ScreenerSnapshot {
  as_of: string | null;
  data_as_of?: string | null;
  generated_at?: string | null;
  model: string | null;
  source?: string | null;
  count: number;
  rows: ScreenerRow[];
  market?: MarketContext | null;
  sessions_behind?: number | null;
  is_stale?: boolean;
}

/** Latest close with as_of + staleness (R6). `symbol` echoes the requested spelling. */
export interface PriceQuote extends LatestClose {
  security_symbol?: string | null;
  sessions_behind?: number | null;
  is_stale?: boolean;
}

export async function fetchCloses(symbols: string[]): Promise<PriceQuote[]> {
  if (symbols.length === 0) return [];
  const qs = encodeURIComponent(symbols.join(','));
  const res = await fetchWithAuth(`${API_BASE}/market/closes?symbols=${qs}`);
  if (!res.ok) throw new Error(`Failed to fetch prices (${res.status})`);
  return res.json();
}

export interface BenchmarkHealth {
  code: string;
  last_date: string | null;
  last_session: string | null;
  sessions_behind: number;
  is_alarm: boolean;
}

export async function fetchThesis(clientId: string, symbol: string): Promise<StockThesis | null> {
  const res = await fetchWithAuth(`${API_BASE}/research/theses/${clientId}/${encodeURIComponent(symbol)}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Failed to load thesis (${res.status})`);
  return res.json();
}

export async function saveThesis(clientId: string, symbol: string, thesis: Thesis): Promise<StockThesis> {
  const res = await fetchWithAuth(`${API_BASE}/research/theses/${clientId}/${encodeURIComponent(symbol)}`, undefined, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ thesis }),
  });
  if (!res.ok) throw new Error(`Failed to save thesis (${res.status})`);
  return res.json();
}

export async function fetchScreenerLatest(model?: string): Promise<ScreenerSnapshot> {
  const q = model ? `?model=${encodeURIComponent(model)}` : '';
  const res = await fetchWithAuth(`${API_BASE}/research/screener/latest${q}`);
  if (!res.ok) throw new Error(`Failed to load screener (${res.status})`);
  return res.json();
}

export async function fetchBenchmarkHealth(): Promise<BenchmarkHealth[]> {
  const res = await fetchWithAuth(`${API_BASE}/market/benchmarks/health`);
  if (!res.ok) throw new Error(`Failed to load market data health (${res.status})`);
  return res.json();
}
