/**
 * Ledger write/read endpoints added for v2 UI parity: dividends and manual trades.
 * Kept separate from api.ts so parallel edits don't collide.
 */
import { fetchWithAuth } from '@/lib/api';

const API_BASE = '/api/v1';

export interface DividendItem {
  dividend_id: number;
  client_id: string;
  symbol: string;
  ex_date: string;
  amount_per_share: number;
  quantity: number;
  amount: number;
  source: 'manual' | 'nse';
}

export interface DividendCreate {
  client_id: string;
  symbol: string;
  ex_date: string;
  amount_per_share: number;
  quantity: number;
}

export interface ManualTradeCreate {
  client_id: string;
  symbol: string;
  exchange: 'NSE' | 'BSE';
  trade_date: string;
  trade_type: 'buy' | 'sell';
  quantity: number;
  price: number;
  note?: string | null;
  idempotency_key?: string;
}

export interface ManualTradeResult {
  trade_id: number | null;
  created: boolean;
  recomputed: boolean;
}

async function errorText(res: Response, fallback: string): Promise<string> {
  const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
  return typeof body.detail === 'string' ? body.detail : `${fallback} (${res.status})`;
}

function jsonInit(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}

export async function fetchDividends(clientId: string): Promise<DividendItem[]> {
  const res = await fetchWithAuth(`${API_BASE}/ledger/dividends?client_id=${encodeURIComponent(clientId)}`);
  if (!res.ok) throw new Error(await errorText(res, 'Failed to load dividends'));
  return res.json();
}

export async function createDividend(data: DividendCreate): Promise<DividendItem> {
  const res = await fetchWithAuth(`${API_BASE}/ledger/dividends`, undefined, jsonInit('POST', data));
  if (!res.ok) throw new Error(await errorText(res, 'Failed to add dividend'));
  return res.json();
}

/** A proposed dividend from a stored corporate action; recorded only when accepted. */
export interface DividendSuggestion {
  symbol: string;
  ex_date: string;
  amount_per_share: number;
  estimated_quantity: number;
  estimated_total: number;
  subject?: string | null;
  source?: string | null;
}

export async function fetchDividendSuggestions(clientId: string): Promise<DividendSuggestion[]> {
  const res = await fetchWithAuth(`${API_BASE}/ledger/dividends/suggestions?client_id=${encodeURIComponent(clientId)}`);
  if (!res.ok) throw new Error(await errorText(res, 'Failed to find missing dividends'));
  return res.json();
}

export async function deleteDividend(dividendId: number): Promise<void> {
  const res = await fetchWithAuth(`${API_BASE}/ledger/dividends/${dividendId}`, undefined, { method: 'DELETE' });
  if (!res.ok) throw new Error(await errorText(res, 'Failed to delete dividend'));
}

export async function createManualTrade(data: ManualTradeCreate): Promise<ManualTradeResult> {
  const res = await fetchWithAuth(`${API_BASE}/ledger/trades/manual`, undefined, jsonInit('POST', data));
  if (!res.ok) throw new Error(await errorText(res, 'Failed to add trade'));
  return res.json();
}

export async function voidManualTrade(tradeId: number): Promise<void> {
  const res = await fetchWithAuth(`${API_BASE}/ledger/trades/${tradeId}`, undefined, { method: 'DELETE' });
  if (!res.ok) throw new Error(await errorText(res, 'Failed to delete trade'));
}

/** DB stores 'buy'/'sell'; older typings say 'BUY'/'SELL'. Compare case-insensitively. */
export function isBuy(tradeType: string): boolean {
  return tradeType.toLowerCase() === 'buy';
}
