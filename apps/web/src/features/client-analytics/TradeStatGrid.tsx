import React from 'react';
import { formatRate, formatRupees } from '@/lib/api';
import type { TradeAnalytics } from '@/lib/apiAnalytics';
import { Stat, toneOf } from './Stat';

const num = (v: number | null, d = 2) => (v != null ? v.toFixed(d) : '—');

export const TradeStatGrid: React.FC<{ a: TradeAnalytics }> = ({ a }) => (
  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
    <Stat label="Closed trades" value={String(a.closed_trades)} hint={`${a.winning_trades} won · ${a.losing_trades} lost · ${a.breakeven_trades} flat`} />
    <Stat label="Win rate" value={formatRate(a.win_rate, 1)} hint="Wins ÷ trades (₹0 is neither)" />
    <Stat label="Profit factor" value={num(a.profit_factor)} hint={a.profit_factor == null ? 'No losing trades' : 'Gross wins ÷ gross losses'} />
    <Stat label="Expectancy" value={formatRupees(a.expectancy, 0)} hint="Average P&L per trade" tone={toneOf(a.expectancy)} />
    <Stat label="Average win" value={formatRupees(a.avg_win, 0)} />
    <Stat label="Average loss" value={a.avg_loss != null ? formatRupees(-a.avg_loss, 0) : '—'} tone={a.avg_loss ? 'neg' : undefined} />
    <Stat label="Avg holding" value={a.avg_holding_days != null ? `${a.avg_holding_days.toFixed(1)} days` : '—'} />
    <Stat label="Realised P&L" value={formatRupees(a.total_pnl, 0)} tone={toneOf(a.total_pnl)} />
  </div>
);
