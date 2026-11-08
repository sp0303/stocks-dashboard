import React, { useMemo } from 'react';
import { formatRupees, formatPercent, type DailySeriesPoint } from '@/lib/api';
import { Calendar } from 'lucide-react';

interface PnlCalendarProps {
  series: DailySeriesPoint[];
}

export const PnlCalendar: React.FC<PnlCalendarProps> = ({ series }) => {
  // Compute daily P&L delta from consecutive daily snapshots
  const dailyPnls = useMemo(() => {
    if (!series || series.length < 2) return [];
    const items = [];
    for (let i = 1; i < series.length; i++) {
      const prev = series[i - 1];
      const curr = series[i];
      // Day P&L delta
      const pnlDelta = (curr.realized_pnl + (curr.market_value - curr.open_cost)) -
                       (prev.realized_pnl + (prev.market_value - prev.open_cost));
      const dayReturn = curr.day_return ?? (prev.nav > 0 ? (curr.nav - prev.nav) / prev.nav : 0);
      items.push({
        date: curr.as_of,
        pnl: pnlDelta,
        dayReturn,
        nav: curr.nav,
      });
    }
    return items.reverse(); // latest first
  }, [series]);

  if (dailyPnls.length === 0) {
    return (
      <div className="p-8 bg-paper border border-hairline rounded-card text-center text-subtle text-xs">
        Insufficient daily trading calendar history to render P&L calendar.
      </div>
    );
  }

  return (
    <div className="bg-paper border border-hairline rounded-card overflow-hidden shadow-sm">
      <div className="p-5 border-b border-hairline flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Calendar className="w-5 h-5 text-subtle" />
          <h2 className="text-base font-semibold text-ink">Daily P&L Performance History (Rule R7 & R11)</h2>
        </div>
        <span className="text-xs text-subtle font-mono">{dailyPnls.length} Trading Sessions</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-sm">
          <thead>
            <tr className="bg-canvas/60 text-subtle text-xs border-b border-hairline">
              <th className="py-3 px-4 font-semibold">Date</th>
              <th className="py-3 px-4 font-semibold text-right">Daily P&L Delta</th>
              <th className="py-3 px-4 font-semibold text-right">Day Return %</th>
              <th className="py-3 px-4 font-semibold text-right">Portfolio NAV</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {dailyPnls.map((d) => {
              const isPos = d.pnl >= 0;
              return (
                <tr key={d.date} className="hover:bg-canvas/50 transition-colors">
                  <td className="py-2.5 px-4 font-mono text-xs text-ink">{d.date}</td>
                  <td className={`py-2.5 px-4 text-right font-mono text-xs font-semibold ${isPos ? 'text-positive' : 'text-negative'}`}>
                    {formatRupees(d.pnl)}
                  </td>
                  <td className={`py-2.5 px-4 text-right font-mono text-xs font-medium ${isPos ? 'text-positive' : 'text-negative'}`}>
                    {formatPercent(d.dayReturn)}
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono text-xs text-ink">
                    {d.nav.toFixed(2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
