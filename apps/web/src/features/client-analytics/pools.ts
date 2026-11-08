import type { Pool } from '@/lib/apiAnalytics';

export const POOLS: { key: Pool; label: string; title: string }[] = [
  { key: 'delivery', label: 'Delivery', title: 'Investment trades (same-day round trips removed)' },
  { key: 'intraday', label: 'Intraday', title: 'Same-day round trips: a separate pool (R9)' },
];
