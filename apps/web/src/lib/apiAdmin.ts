/**
 * Super-admin + manager-book API calls (modules/admin on the backend).
 * Ratios are decimals (R12); `null` means unknown, never zero.
 */
import { fetchWithAuth, type ManagerItem } from '@/lib/api';

const API_BASE = '/api/v1';

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetchWithAuth(`${API_BASE}${path}`, undefined, {
    ...init,
    headers: init?.body ? { 'Content-Type': 'application/json', ...(init?.headers ?? {}) } : init?.headers,
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: unknown };
    const detail = typeof err.detail === 'string' ? err.detail : `Request failed (${res.status})`;
    throw new Error(detail);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

// ------------------------------------------------------------------ super-admin

export interface PlatformOverviewV2 {
  total_market_value: number;
  total_capital_deployed: number;
  total_pnl: number;
  client_count: number;
  manager_count: number;
  trade_count: number;
}

export interface CorporateActionsRun {
  run_id: number;
  started_at: string;
  finished_at?: string | null;
  status: 'RUNNING' | 'OK' | 'FAILED' | 'SKIPPED';
  rows_in?: number | null;
  rows_out?: number | null;
  error?: string | null;
  meta?: Record<string, unknown> | null;
}

export interface CorporateActionsStatus {
  actions: number;
  symbols: number;
  last_fetched_at?: string | null;
  last_run?: CorporateActionsRun | null;
}

export const fetchPlatformOverview = () => call<PlatformOverviewV2>('/admin/overview');
export const fetchManagers = () => call<ManagerItem[]>('/admin/managers');
export const updateManager = (
  id: string,
  data: { name?: string; firm?: string; email?: string; is_active?: boolean },
) => call<ManagerItem>(`/admin/managers/${id}`, json('PATCH', data));
export const deleteManager = (id: string) => call<void>(`/admin/managers/${id}`, json('DELETE'));
export const fetchCorporateActionsStatus = () => call<CorporateActionsStatus>('/admin/corporate-actions/status');
export const requestCorporateActionsRefresh = (scope: 'held' | 'all') =>
  call<{ accepted: boolean; scope: string; message_id: string }>(
    '/admin/corporate-actions/refresh',
    json('POST', { scope }),
  );

// ------------------------------------------------------------------ manager book

export type Broker = 'ZERODHA' | 'UPSTOX' | 'ANGEL' | 'OTHER';

export interface BookRosterItem {
  client_id: string;
  name: string;
  client_code?: string | null;
  broker?: Broker | null;
  status: string;
  as_of?: string | null;
  computed: boolean;
  trade_count: number;
  market_value?: number | null;
  capital_deployed?: number | null;
  current_invested?: number | null;
  realized_pnl?: number | null;
  unrealized_pnl?: number | null;
  total_pnl?: number | null;
  return_on_capital?: number | null;
}

export interface SymbolStat {
  symbol: string;
  value: number;
}

export interface BookSummary {
  manager_id: string;
  as_of?: string | null;
  totals: {
    client_count: number;
    market_value: number;
    capital_deployed: number;
    current_invested: number;
    realized_pnl: number;
    unrealized_pnl: number;
    total_pnl: number;
    return_on_capital?: number | null;
  };
  insights: {
    unique_stocks: number;
    unpriced_symbols: string[];
    most_invested?: SymbolStat | null;
    most_traded?: SymbolStat | null;
    top_holding?: SymbolStat | null;
    best_performer?: SymbolStat | null;
    worst_performer?: SymbolStat | null;
  };
  clients: BookRosterItem[];
}

export interface BenchmarkPnl {
  code: string;
  label: string;
  points: (number | null)[];
  last_date?: string | null;
  sessions_behind: number;
  stale: boolean;
}

export interface BookPerformance {
  dates: string[];
  book_pnl: number[];
  net_invested: number[];
  benchmarks: BenchmarkPnl[];
}

export interface ClientReturnSeries {
  client_id: string;
  name: string;
  series: { as_of: string; value: number }[];
}

export interface ClosedTrade {
  client_id: string;
  client_name: string;
  client_code?: string | null;
  symbol: string;
  buy_date: string;
  sell_date: string;
  quantity: number;
  buy_price: number;
  sell_price: number;
  pnl: number;
  pnl_pct?: number | null;
  days: number;
}

export interface ClientInput {
  name?: string;
  client_code?: string | null;
  broker?: Broker | null;
  manager_id?: string;
}

export interface BookClient {
  client_id: string;
  manager_id: string;
  name: string;
  client_code?: string | null;
  broker?: string | null;
  status: string;
  created_at: string;
}

export const fetchBookSummary = (mid: string) => call<BookSummary>(`/book/managers/${mid}/summary`);
export const fetchBookPerformance = (mid: string) => call<BookPerformance>(`/book/managers/${mid}/performance`);
export const fetchClientReturns = (mid: string) => call<ClientReturnSeries[]>(`/book/managers/${mid}/client-returns`);
export const fetchClosedTrades = (mid: string) => call<ClosedTrade[]>(`/book/managers/${mid}/closed-trades`);
export const createBookClient = (mid: string, data: ClientInput) =>
  call<BookClient>(`/book/managers/${mid}/clients`, json('POST', data));
export const updateBookClient = (cid: string, data: ClientInput) =>
  call<BookClient>(`/book/clients/${cid}`, json('PATCH', data));
export const deleteBookClient = (cid: string) => call<void>(`/book/clients/${cid}`, json('DELETE'));
