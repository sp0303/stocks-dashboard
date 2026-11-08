/**
 * Portfolio Intelligence v2 API client, formatters, and silent token refresh interceptor.
 * Adheres strictly to Rule R12: ratios are decimals, UI formatter multiplies by 100.
 */

import { useAuthStore } from '@/stores/authStore';

export interface ClientSummary {
  client_id: string;
  name: string;
  client_code?: string;
  broker?: string;
  status: string;
  market_value: number;
  capital_deployed: number;
  current_invested: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_pnl: number;
  return_on_capital: number;
  cagr?: number | null;
  as_of?: string;
  /** R6.4: holdings with no usable price, excluded from current_invested and market_value */
  unpriced?: UnpricedHolding[];
  unpriced_cost?: number;
  /** priced + unpriced open holdings — the same rows as the holdings table */
  open_positions?: number | null;
  priced_positions?: number | null;
  /** R9: same-day round trips and F&O report P&L only, never capital */
  intraday?: { trades: number; pnl: number } | null;
  derivatives?: { trades: number; pnl: number } | null;
  warnings?: string[];
}

export interface UnpricedHolding {
  symbol: string;
  exchange: string;
  quantity: number;
  cost: number;
}

export interface PositionItem {
  security_id: number;
  symbol: string;
  exchange: string;
  quantity: number;
  avg_cost: number;
  invested: number;
  /** null when unpriced (R6): never cost */
  current_price?: number | null;
  market_value?: number | null;
  unrealized_pnl?: number | null;
  return_pct?: number | null;
  entry_date?: string;
  /** false = no usable price: excluded from cost and value (R6.4) */
  priced?: boolean;
  price_as_of?: string | null;
  /** set when valued at the other exchange's close (ADR-0009) */
  priced_on?: string | null;
}

export interface DailySeriesPoint {
  as_of: string;
  market_value: number;
  open_cost: number;
  net_invested: number;
  realized_pnl: number;
  nav: number;
  day_return?: number;
}

export interface ClientMetrics {
  client_id: string;
  as_of: string;
  total_return: number;
  cagr?: number | null;
  annualized_volatility?: number | null;
  sharpe_ratio?: number | null;
  max_drawdown?: number | null;
  current_drawdown?: number | null;
  beta?: number | null;
  alpha?: number | null;
  xirr?: number | null;
}

export interface ManagerMetrics {
  manager_id: string;
  client_count: number;
  total_capital_deployed: number;
  total_market_value: number;
  total_current_invested: number;
  total_realized_pnl: number;
  total_unrealized_pnl: number;
  total_pnl: number;
  return_on_capital: number;
  weighted_volatility?: number | null;
  weighted_sharpe?: number | null;
  max_drawdown?: number | null;
  as_of?: string | null;
  /** Book time-weighted metrics (R2/R3/R5), decimals (R12); null = not enough data */
  book_total_return?: number | null;
  book_cagr?: number | null;
  book_volatility?: number | null;
  book_sharpe?: number | null;
  book_max_drawdown?: number | null;
  book_current_drawdown?: number | null;
  book_observations?: number;
  book_series_start?: string | null;
  book_series_end?: string | null;
}

export interface TradeItem {
  trade_id: number;
  client_id: string;
  client_name?: string | null;
  client_code?: string | null;
  symbol: string;
  exchange: string;
  trade_date: string;
  trade_type: 'BUY' | 'SELL';
  quantity: number;
  price: number;
  trade_value: number;
  charges?: number | null;
  charges_known: boolean;
  segment: string;
  broker_trade_id?: string | null;
  broker_order_id?: string | null;
  source: string;
  created_at: string;
}

export interface CorporateActionItem {
  action_id: number;
  key: string;
  symbol: string;
  isin?: string | null;
  ex_date: string;
  type: string;
  qty_multiplier?: number | null;
  amount_per_share?: number | null;
  subject?: string | null;
  source: string;
  fetched_at: string;
}

export interface BenchmarkSeriesPoint {
  as_of: string;
  value: number;
  source: string;
}


export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token: string;
}

export interface MeResponse {
  user_id: string;
  email: string;
  role: string;
  manager_id: string | null;
  client_id: string | null;
}

export interface UploadTradebookResponse {
  upload_id: string;
  rows_total: number;
  rows_imported: number;
  rows_duplicate?: number;
  rows_rejected: number;
  status: string;
}

export interface WatchlistEntryItem {
  symbol: string;
  added_date: string;
  added_price?: number | null;
  why?: string | null;
  remarks?: string | null;
  risks?: string | null;
  sector?: string | null;
  alert_price?: number | null;
}

export interface WatchlistResponse {
  watchlist_id: string;
  owner_type: string;
  owner_id: string;
  name: string;
  is_default: boolean;
  entries: WatchlistEntryItem[];
}

export interface WatchlistCreate {
  owner_type?: string;
  owner_id: string;
  name: string;
  is_default?: boolean;
}

export interface WatchlistEntryAdd {
  symbol: string;
  added_price?: number | null;
  why?: string | null;
  remarks?: string | null;
  risks?: string | null;
  sector?: string | null;
  alert_price?: number | null;
}

export interface BoardItemResponse {
  item_id: string;
  owner_type: string;
  owner_id: string;
  symbol: string;
  lane: 'watching' | 'holding' | 'exit';
  entry_price?: number | null;
  exit_price?: number | null;
  why?: string | null;
  colour?: string | null;
  sort_order: number;
}

export interface BoardItemCreate {
  owner_type?: string;
  owner_id: string;
  symbol: string;
  lane?: 'watching' | 'holding' | 'exit';
  entry_price?: number | null;
  exit_price?: number | null;
  why?: string | null;
  colour?: string | null;
  sort_order?: number;
}

export interface BoardItemUpdate {
  lane?: 'watching' | 'holding' | 'exit';
  entry_price?: number | null;
  exit_price?: number | null;
  why?: string | null;
  colour?: string | null;
  sort_order?: number;
}

const API_BASE = '/api/v1';

// -------------------------------------------------------------------------- //
// Silent Token Refresh & Interceptor
// -------------------------------------------------------------------------- //

let refreshPromise: Promise<string | null> | null = null;

export function authHeaders(token: string | null): HeadersInit {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function silentRefreshToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;
  const refreshToken = sessionStorage.getItem('pi_rt');
  if (!refreshToken) return null;

  refreshPromise = (async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (res.ok) {
        const data: LoginResponse = await res.json();
        useAuthStore.getState().setToken(data.access_token, data.expires_in);
        sessionStorage.setItem('pi_rt', data.refresh_token);
        return data.access_token;
      } else {
        useAuthStore.getState().clearToken();
        sessionStorage.removeItem('pi_rt');
        return null;
      }
    } catch {
      return null;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

export async function getValidAccessToken(): Promise<string | null> {
  const { accessToken, expiresAt } = useAuthStore.getState();
  if (!accessToken) return null;
  // If expiring in < 60s, silently renew before request
  if (expiresAt && expiresAt - Date.now() < 60_000) {
    const renewed = await silentRefreshToken();
    if (renewed) return renewed;
  }
  return accessToken;
}

export async function fetchWithAuth(url: string, explicitToken?: string | null, init?: RequestInit): Promise<Response> {
  let token = explicitToken ?? (await getValidAccessToken());
  let res = await fetch(url, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      ...authHeaders(token),
    },
  });

  // Interceptor: if 401/403, attempt a silent refresh and retry once
  if (res.status === 401 || res.status === 403) {
    const newToken = await silentRefreshToken();
    if (newToken) {
      res = await fetch(url, {
        ...init,
        headers: {
          ...(init?.headers ?? {}),
          ...authHeaders(newToken),
        },
      });
    }
  }

  return res;
}

// -------------------------------------------------------------------------- //
// Auth endpoints
// -------------------------------------------------------------------------- //

export async function apiLogin(email: string, password: string): Promise<LoginResponse> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? 'Login failed');
  }
  return res.json();
}

export async function apiRefresh(refreshToken: string): Promise<LoginResponse> {
  const res = await fetch(`${API_BASE}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!res.ok) throw new Error('Session expired');
  return res.json();
}

export async function apiLogout(token: string | null, refreshToken: string): Promise<void> {
  await fetchWithAuth(`${API_BASE}/auth/logout`, token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
}

export async function apiChangePassword(currentPassword: string, newPassword: string): Promise<void> {
  const res = await fetchWithAuth(`${API_BASE}/auth/change-password`, null, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: unknown };
    const detail = typeof err.detail === 'string' ? err.detail : 'Could not change password';
    throw new Error(detail);
  }
}

// -------------------------------------------------------------------------- //
// Portfolio endpoints
// -------------------------------------------------------------------------- //

export async function fetchClients(token?: string | null, managerId?: string | null): Promise<ClientSummary[]> {
  const url = managerId ? `${API_BASE}/portfolio/clients?manager_id=${managerId}` : `${API_BASE}/portfolio/clients`;
  const res = await fetchWithAuth(url, token);
  if (!res.ok) throw new Error(`Failed to fetch clients: ${res.statusText}`);
  return res.json();
}

export async function fetchClientOverview(clientId: string, token?: string | null): Promise<ClientSummary> {
  const res = await fetchWithAuth(`${API_BASE}/portfolio/clients/${clientId}/overview`, token);
  if (!res.ok) throw new Error(`Failed to fetch client overview: ${res.statusText}`);
  return res.json();
}

export async function fetchClientPositions(clientId: string, token?: string | null): Promise<PositionItem[]> {
  const res = await fetchWithAuth(`${API_BASE}/portfolio/clients/${clientId}/positions`, token);
  if (!res.ok) throw new Error(`Failed to fetch positions: ${res.statusText}`);
  return res.json();
}

export async function fetchClientSeries(clientId: string, token?: string | null): Promise<DailySeriesPoint[]> {
  const res = await fetchWithAuth(`${API_BASE}/portfolio/clients/${clientId}/series`, token);
  if (!res.ok) throw new Error(`Failed to fetch series: ${res.statusText}`);
  return res.json();
}

export async function fetchClientMetrics(clientId: string, token?: string | null): Promise<ClientMetrics> {
  const res = await fetchWithAuth(`${API_BASE}/portfolio/clients/${clientId}/metrics`, token);
  if (!res.ok) throw new Error(`Failed to fetch metrics: ${res.statusText}`);
  return res.json();
}

export async function fetchManagerMetrics(managerId: string, token?: string | null): Promise<ManagerMetrics> {
  const res = await fetchWithAuth(`${API_BASE}/portfolio/managers/${managerId}/metrics`, token);
  if (!res.ok) throw new Error(`Failed to fetch manager metrics: ${res.statusText}`);
  return res.json();
}

export async function fetchTrades(
  params: {
    clientId?: string;
    managerId?: string;
    symbol?: string;
    side?: string;
    startDate?: string;
    endDate?: string;
    limit?: number;
    offset?: number;
  },
  token?: string | null
): Promise<TradeItem[]> {
  const q = new URLSearchParams();
  if (params.clientId) q.set('client_id', params.clientId);
  if (params.managerId) q.set('manager_id', params.managerId);
  if (params.symbol) q.set('symbol', params.symbol);
  if (params.side) q.set('side', params.side);
  if (params.startDate) q.set('start_date', params.startDate);
  if (params.endDate) q.set('end_date', params.endDate);
  if (params.limit) q.set('limit', String(params.limit));
  if (params.offset) q.set('offset', String(params.offset));

  const endpoint = params.clientId ? `${API_BASE}/ledger/trades` : `${API_BASE}/ledger/manager-trades`;
  const res = await fetchWithAuth(`${endpoint}?${q.toString()}`, token);
  if (!res.ok) throw new Error(`Failed to fetch trades: ${res.statusText}`);
  return res.json();
}


export async function fetchCorporateActions(
  params?: {
    symbol?: string;
    type?: string;
    startDate?: string;
    endDate?: string;
    limit?: number;
    offset?: number;
  },
  token?: string | null
): Promise<CorporateActionItem[]> {
  const q = new URLSearchParams();
  if (params?.symbol) q.set('symbol', params.symbol);
  if (params?.type) q.set('type', params.type);
  if (params?.startDate) q.set('start_date', params.startDate);
  if (params?.endDate) q.set('end_date', params.endDate);
  if (params?.limit) q.set('limit', String(params.limit));
  if (params?.offset) q.set('offset', String(params.offset));

  const res = await fetchWithAuth(`${API_BASE}/ledger/corporate-actions?${q.toString()}`, token);
  if (!res.ok) throw new Error(`Failed to fetch corporate actions: ${res.statusText}`);
  return res.json();
}

export async function fetchBenchmarkSeries(
  code: string,
  startDate?: string,
  endDate?: string,
  token?: string | null
): Promise<BenchmarkSeriesPoint[]> {
  const q = new URLSearchParams();
  if (startDate) q.set('start_date', startDate);
  if (endDate) q.set('end_date', endDate);

  const res = await fetchWithAuth(`${API_BASE}/market/benchmarks/${code}/series?${q.toString()}`, token);
  if (!res.ok) throw new Error(`Failed to fetch benchmark series: ${res.statusText}`);
  return res.json();
}

// -------------------------------------------------------------------------- //
// Ledger endpoints
// -------------------------------------------------------------------------- //


export async function uploadTradebook(
  clientId: string,
  brokerFormat: string,
  file: File,
  token?: string | null
): Promise<UploadTradebookResponse> {
  const formData = new FormData();
  formData.append('client_id', clientId);
  formData.append('broker_format', brokerFormat);
  formData.append('file', file);

  const res = await fetchWithAuth(`${API_BASE}/ledger/upload`, token, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? `Upload failed with status ${res.status}`);
  }
  return res.json();
}

// -------------------------------------------------------------------------- //
// Research endpoints
// -------------------------------------------------------------------------- //

export async function fetchWatchlists(ownerId: string, token?: string | null): Promise<WatchlistResponse[]> {
  const res = await fetchWithAuth(`${API_BASE}/research/watchlists?owner_id=${ownerId}`, token);
  if (!res.ok) throw new Error(`Failed to fetch watchlists: ${res.statusText}`);
  return res.json();
}

export async function createWatchlist(data: WatchlistCreate, token?: string | null): Promise<WatchlistResponse> {
  const res = await fetchWithAuth(`${API_BASE}/research/watchlists`, token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to create watchlist: ${res.statusText}`);
  return res.json();
}

export async function addWatchlistEntry(
  watchlistId: string,
  entry: WatchlistEntryAdd,
  token?: string | null
): Promise<void> {
  const res = await fetchWithAuth(`${API_BASE}/research/watchlists/${watchlistId}/entries`, token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(entry),
  });
  if (!res.ok) throw new Error(`Failed to add symbol: ${res.statusText}`);
}

export async function deleteWatchlistEntry(
  watchlistId: string,
  symbol: string,
  token?: string | null
): Promise<void> {
  const res = await fetchWithAuth(`${API_BASE}/research/watchlists/${watchlistId}/entries/${symbol}`, token, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Failed to delete entry: ${res.statusText}`);
}

export async function fetchBoard(ownerId: string, token?: string | null): Promise<BoardItemResponse[]> {
  const res = await fetchWithAuth(`${API_BASE}/research/board?owner_id=${ownerId}`, token);
  if (!res.ok) throw new Error(`Failed to fetch board: ${res.statusText}`);
  return res.json();
}

export async function createBoardItem(item: BoardItemCreate, token?: string | null): Promise<BoardItemResponse> {
  const res = await fetchWithAuth(`${API_BASE}/research/board/items`, token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(item),
  });
  if (!res.ok) throw new Error(`Failed to create board card: ${res.statusText}`);
  return res.json();
}

export async function updateBoardItem(
  itemId: string,
  item: BoardItemUpdate,
  token?: string | null
): Promise<BoardItemResponse> {
  const res = await fetchWithAuth(`${API_BASE}/research/board/items/${itemId}`, token, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(item),
  });
  if (!res.ok) throw new Error(`Failed to update board card: ${res.statusText}`);
  return res.json();
}

export async function deleteBoardItem(itemId: string, token?: string | null): Promise<void> {
  const res = await fetchWithAuth(`${API_BASE}/research/board/items/${itemId}`, token, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Failed to delete card: ${res.statusText}`);
}

// -------------------------------------------------------------------------- //
// Manager Holdings & CSV Export
// -------------------------------------------------------------------------- //

export interface ManagerHoldingsItem {
  security_id: number;
  symbol: string;
  exchange: string;
  quantity: number;
  avg_cost: number;
  invested: number;
  client_count: number;
  /** null = unpriced (R6): value and P&L are unknown, never cost. */
  current_price?: number | null;
  price_as_of?: string | null;
  priced_on?: string | null;
  market_value?: number | null;
  unrealized_pnl?: number | null;
  return_pct?: number | null;
  clients?: HoldingClientItem[];
}

export interface HoldingClientItem {
  client_id: string;
  name: string;
  quantity: number;
  invested: number;
}

export async function fetchManagerHoldings(managerId: string, token?: string | null): Promise<ManagerHoldingsItem[]> {
  const res = await fetchWithAuth(`${API_BASE}/portfolio/managers/${managerId}/holdings`, token);
  if (!res.ok) throw new Error(`Failed to fetch manager holdings: ${res.statusText}`);
  return res.json();
}

export interface LatestClose {
  symbol: string;
  exchange: string;
  price: number;
  price_date: string;
  source: string;
}

/** Latest stored daily close per symbol; symbols without a price are simply absent (R6). */
export async function fetchLatestCloses(symbols: string[], token?: string | null): Promise<LatestClose[]> {
  if (symbols.length === 0) return [];
  const qs = encodeURIComponent(symbols.join(','));
  const res = await fetchWithAuth(`${API_BASE}/market/closes?symbols=${qs}`, token);
  if (!res.ok) throw new Error(`Failed to fetch prices: ${res.statusText}`);
  return res.json();
}

export async function exportTradebookCsv(clientId: string, token?: string | null): Promise<Blob> {
  const res = await fetchWithAuth(`${API_BASE}/ledger/export/${clientId}`, token);
  if (!res.ok) throw new Error(`Failed to export tradebook: ${res.statusText}`);
  return res.blob();
}

// -------------------------------------------------------------------------- //
// Admin endpoints
// -------------------------------------------------------------------------- //

export interface PlatformOverview {
  total_market_value: number;
  total_capital_deployed: number;
  total_pnl: number;
  client_count: number;
  manager_count: number;
}

export interface ManagerItem {
  manager_id: string;
  name: string;
  email: string;
  firm?: string | null;
  is_active: boolean;
  client_count: number;
  created_at: string;
}

export async function fetchAdminOverview(token?: string | null): Promise<PlatformOverview> {
  const res = await fetchWithAuth(`${API_BASE}/admin/overview`, token);
  if (!res.ok) throw new Error(`Failed to fetch admin overview: ${res.statusText}`);
  return res.json();
}

export async function fetchAdminManagers(token?: string | null): Promise<ManagerItem[]> {
  const res = await fetchWithAuth(`${API_BASE}/admin/managers`, token);
  if (!res.ok) throw new Error(`Failed to fetch managers: ${res.statusText}`);
  return res.json();
}

export async function createAdminManager(
  data: { name: string; email: string; firm?: string; password?: string },
  token?: string | null
): Promise<ManagerItem> {
  const res = await fetchWithAuth(`${API_BASE}/admin/managers`, token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? `Failed to create manager`);
  }
  return res.json();
}

export async function updateAdminManager(
  managerId: string,
  data: { name?: string; firm?: string; is_active?: boolean },
  token?: string | null
): Promise<ManagerItem> {
  const res = await fetchWithAuth(`${API_BASE}/admin/managers/${managerId}`, token, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to update manager: ${res.statusText}`);
  return res.json();
}

export async function reassignClientManager(
  clientId: string,
  newManagerId: string,
  token?: string | null
): Promise<void> {
  const res = await fetchWithAuth(`${API_BASE}/admin/clients/${clientId}/reassign`, token, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ manager_id: newManagerId }),
  });
  if (!res.ok) throw new Error(`Failed to reassign client: ${res.statusText}`);
}

// -------------------------------------------------------------------------- //
// Formatters
// -------------------------------------------------------------------------- //

export function formatRupees(amount: number | null | undefined, decimals = 2): string {
  if (amount == null || isNaN(amount)) return '—';
  const isNeg = amount < 0;
  const absVal = Math.abs(amount).toLocaleString('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return `${isNeg ? '−₹ ' : '₹ '}${absVal}`;
}

/** A rate or share (win rate, weight): decimal -> "88.0%", never signed. Use formatPercent for changes. */
export function formatRate(decimal: number | null | undefined, decimals = 1): string {
  if (decimal == null || isNaN(decimal)) return '—';
  return `${(decimal * 100).toFixed(decimals)}%`;
}

export function formatPercent(decimal: number | null | undefined, decimals = 2): string {
  if (decimal == null || isNaN(decimal)) return '—';
  const pct = decimal * 100;
  const sign = pct > 0 ? '+' : pct < 0 ? '−' : '';
  return `${sign}${Math.abs(pct).toFixed(decimals)}%`;
}
