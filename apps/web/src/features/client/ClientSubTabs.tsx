import React from 'react';
import { Activity, BookOpen, Briefcase, Calendar, CalendarClock, Coins, Eye, History, LineChart, PieChart } from 'lucide-react';
import type { AnalyticsTabKey } from '@/features/client-analytics';

export type ClientTab = 'positions' | 'trades' | 'dividends' | 'calendar' | AnalyticsTabKey;

interface Props {
  active: ClientTab;
  positionsCount: number;
  onChange: (tab: ClientTab) => void;
}

export const ClientSubTabs: React.FC<Props> = ({ active, positionsCount, onChange }) => {
  const tabs: { key: ClientTab; label: string; icon: React.ReactNode }[] = [
    { key: 'positions', label: `Holdings & Positions (${positionsCount})`, icon: <Briefcase className="w-3.5 h-3.5" aria-hidden /> },
    { key: 'trades', label: 'Trade History', icon: <History className="w-3.5 h-3.5" aria-hidden /> },
    { key: 'dividends', label: 'Dividends', icon: <Coins className="w-3.5 h-3.5" aria-hidden /> },
    { key: 'calendar', label: 'Daily P&L Calendar (R7)', icon: <Calendar className="w-3.5 h-3.5" aria-hidden /> },
    { key: 'performance', label: 'Performance', icon: <LineChart className="w-3.5 h-3.5" aria-hidden /> },
    { key: 'allocation', label: 'Allocation', icon: <PieChart className="w-3.5 h-3.5" aria-hidden /> },
    { key: 'trade-analytics', label: 'Trade Analytics', icon: <Activity className="w-3.5 h-3.5" aria-hidden /> },
    { key: 'playbook', label: 'Playbook', icon: <BookOpen className="w-3.5 h-3.5" aria-hidden /> },
    { key: 'corporate-actions', label: 'Corporate Actions', icon: <CalendarClock className="w-3.5 h-3.5" aria-hidden /> },
    { key: 'watchlist', label: 'Watchlist', icon: <Eye className="w-3.5 h-3.5" aria-hidden /> },
  ];
  return (
    <div role="tablist" className="flex items-center gap-2 border-b border-hairline pb-2 overflow-x-auto">
      {tabs.map((t) => (
        <button
          key={t.key}
          role="tab"
          aria-selected={active === t.key}
          type="button"
          onClick={() => onChange(t.key)}
          className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition-colors ${
            active === t.key ? 'bg-ink text-paper' : 'text-subtle hover:text-ink bg-paper border border-hairline'
          }`}
        >
          {t.icon} {t.label}
        </button>
      ))}
    </div>
  );
};
