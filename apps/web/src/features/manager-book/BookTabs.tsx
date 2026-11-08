import React from 'react';
import { BarChart3, Calendar, History, Layers, Users } from 'lucide-react';

export const TABS = {
  clients: { label: 'Clients', icon: Users },
  performance: { label: 'Performance', icon: BarChart3 },
  holdings: { label: 'Holdings', icon: Layers },
  trades: { label: 'Trade log', icon: History },
  'corporate-actions': { label: 'Corporate actions', icon: Calendar },
} as const;
export type BookTab = keyof typeof TABS;

export const BookTabs: React.FC<{ tab: BookTab; onTab: (t: BookTab) => void }> = ({ tab, onTab }) => (
  <div role="tablist" aria-label="Manager book" className="flex items-center gap-2 border-b border-hairline pb-2 overflow-x-auto">
    {(Object.keys(TABS) as BookTab[]).map((id) => {
      const { label, icon: Icon } = TABS[id];
      return (
        <button
          key={id}
          type="button"
          role="tab"
          aria-selected={tab === id}
          onClick={() => onTab(id)}
          className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-interactive text-xs font-semibold whitespace-nowrap ${
            tab === id ? 'bg-ink text-paper' : 'text-subtle hover:text-ink bg-paper border border-hairline'
          }`}
        >
          <Icon className="w-3.5 h-3.5" aria-hidden /> {label}
        </button>
      );
    })}
  </div>
);
