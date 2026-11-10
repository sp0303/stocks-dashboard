import React, { memo } from 'react';
import { formatPercent } from '@/lib/api';
import type { HeatmapTile } from '@/lib/apiHeatmap';
import { CAP, shade } from './heatShade';

const Tile: React.FC<{ t: HeatmapTile }> = memo(({ t }) => {
  const price = t.close != null ? `₹${t.close.toLocaleString('en-IN')}` : 'no price';
  const title = `${t.symbol}: ${formatPercent(t.ret)} · ${price} · ${t.clients} client(s)${t.suspect ? ' · unusual move, check data' : ''}`;
  return (
    <li className="rounded-interactive p-2.5 min-h-[72px] flex flex-col justify-between" style={shade(t.ret, CAP.day)} title={title}>
      <span className="text-xs font-semibold truncate">{t.symbol}{t.suspect ? ' ⚠' : ''}</span>
      <span className="text-sm font-bold tabular-nums">{formatPercent(t.ret)}</span>
      <span className="text-[10px] opacity-80 tabular-nums truncate">{price} · {t.clients}c</span>
    </li>
  );
});
Tile.displayName = 'Tile';

/** One tile per held stock, coloured by that day's move; the value is always printed too. */
export const DayTiles: React.FC<{ tiles: HeatmapTile[] }> = ({ tiles }) => (
  <ul aria-label="Day move per holding" className="grid gap-2 grid-cols-[repeat(auto-fill,minmax(110px,1fr))]">
    {tiles.map((t) => <Tile key={t.symbol} t={t} />)}
  </ul>
);
