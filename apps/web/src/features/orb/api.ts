/**
 * ORB API client (read-only). Prices arrive in rupees, ratios as decimals (R12).
 * Pre-cutover the data is a mirror of v1's ORB engine, synced from v1 Mongo.
 */
import { fetchWithAuth } from '@/lib/api';

const BASE = '/api/v1/orb';

export interface OrbUniverse {
  trade_date: string | null;
  size: number | null;
  min_turnover_cr: number | null;
  pool: unknown;
  sector_mapped: number;
  members: Array<Record<string, unknown>>;
  synced_at: string | null;
}

export interface OrbScreenRow {
  sym: string;
  passed: boolean;
  failed: string | null;
  or_high: number | null;
  or_low: number | null;
  or_width: number | null;
  rvol: number | null;
  turnover_cr: number | null;
}

export interface OrbEntry {
  sym: string | null;
  time: string | null;
  side: 'LONG' | 'SHORT' | null;
  entry: number | null;
  stop: number | null;
  t1: number | null;
  t2: number | null;
  qty: number | null;
  risk: number | null;
}

export interface OrbSignals {
  trade_date: string | null;
  screen: {
    candidates: number | null;
    passed: number | null;
    shortlist: string[];
    rows: OrbScreenRow[];
    config: string | null;
    at: string | null;
  } | null;
  entries: OrbEntry[];
}

export interface OrbHealthSession {
  trade_date: string | null;
  agree_ratio: number | null;
  passes_exit_test: boolean | null;
  symbols: number | null;
  minutes_compared: number | null;
}

export interface OrbHealth {
  source: string;
  last_synced_at: string | null;
  sessions: OrbHealthSession[];
  exit_test: {
    sessions_required: number;
    sessions_scored: number;
    sessions_passing: number;
    worst_agree_ratio: number | null;
    passed: boolean;
  };
  heartbeat: { trade_date: string | null; time: string | null; market_open: boolean | null } | null;
  jobs: Array<{ trade_date: string | null; job: string; ok: boolean | null; detail: string | null }>;
}

export interface OrbJournal {
  since: string;
  count: number;
  total_r: number;
  win_rate: number | null;
  expectancy_r: number | null;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetchWithAuth(`${BASE}${path}`);
  if (!res.ok) throw new Error(`ORB request failed (${res.status})`);
  return res.json() as Promise<T>;
}

const q = (date?: string | null) => (date ? `?date=${encodeURIComponent(date)}` : '');

export const fetchOrbUniverse = (date?: string | null) => getJson<OrbUniverse>(`/universe${q(date)}`);
export const fetchOrbSignals = (date?: string | null) => getJson<OrbSignals>(`/signals${q(date)}`);
export const fetchOrbHealth = () => getJson<OrbHealth>('/health');
export const fetchOrbJournal = () => getJson<OrbJournal>('/journal');
