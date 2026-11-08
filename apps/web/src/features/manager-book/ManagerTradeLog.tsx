import React from 'react';
import { ClosedTradesTable } from './ClosedTradesTable';
import { AllTradesTable } from './AllTradesTable';
import { useUrlParam } from './useBook';

const VIEWS = { closed: 'Closed trades', all: 'All trades' } as const;

/** Trade log parity with v1: closed-trade journal across accounts, plus the raw trade list. */
export const ManagerTradeLog: React.FC<{ managerId: string }> = ({ managerId }) => {
  const [view, setView] = useUrlParam('tl', 'closed');
  return (
    <div className="bg-paper border border-hairline rounded-card overflow-hidden shadow-sm">
      <div className="p-4 border-b border-hairline flex gap-2" role="tablist" aria-label="Trade log view">
        {Object.entries(VIEWS).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={view === id}
            onClick={() => setView(id)}
            className={`px-3 py-1.5 rounded-interactive text-xs font-semibold ${view === id ? 'bg-ink text-paper' : 'text-subtle border border-hairline hover:text-ink'}`}
          >
            {label}
          </button>
        ))}
      </div>
      {view === 'all' ? <AllTradesTable managerId={managerId} /> : <ClosedTradesTable managerId={managerId} />}
    </div>
  );
};
