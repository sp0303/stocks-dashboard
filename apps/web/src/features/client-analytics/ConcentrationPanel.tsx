import React from 'react';
import { formatPercent } from '@/lib/api';
import type { Concentration } from '@/lib/apiAnalytics';
import { Stat } from './Stat';

/** Concentration by market value of priced open holdings (unpriced excluded, R6). */
export const ConcentrationPanel: React.FC<{ c: Concentration }> = ({ c }) => (
  <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
    <Stat label="Top 5 weight" value={formatPercent(c.top5_weight)} hint={`${c.holdings_count} priced holdings`} />
    <Stat label="Top 10 weight" value={formatPercent(c.top10_weight)} />
    <Stat
      label="Largest stock"
      value={c.largest_stock ? `${c.largest_stock.symbol} · ${formatPercent(c.largest_stock.weight)}` : '—'}
    />
    <Stat
      label="Largest sector"
      value={c.largest_sector ? `${c.largest_sector.key} · ${formatPercent(c.largest_sector.weight)}` : '—'}
    />
  </div>
);
