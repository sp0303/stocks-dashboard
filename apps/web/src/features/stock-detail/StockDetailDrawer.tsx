import React, { useEffect, useRef } from 'react';
import { SymbolWithExchange } from '@/components/ExchangeBadge';
import { X } from 'lucide-react';
import type { PositionItem } from '@/lib/api';
import { useAuthStore } from '@/stores/authStore';
import { PositionSummary } from './PositionSummary';
import { SymbolTrades } from './SymbolTrades';
import { ThesisPanel } from './ThesisPanel';

interface Props {
  clientId: string;
  position: PositionItem;
  onClose: () => void;
}

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <section className="space-y-2">
    <h3 className="text-xs font-semibold uppercase tracking-wider text-subtle">{title}</h3>
    {children}
  </section>
);

/** Right-hand drawer for one holding: position & P&L, the client's trades in it, and the thesis. */
export const StockDetailDrawer: React.FC<Props> = ({ clientId, position, onClose }) => {
  const role = useAuthStore((s) => s.role);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/40" onClick={onClose}>
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`${position.symbol} details`}
        className="h-full w-full max-w-lg bg-paper border-l border-hairline shadow-xl overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="sticky top-0 bg-paper border-b border-hairline px-5 py-4 flex items-center justify-between">
          <div>
            <SymbolWithExchange symbol={position.symbol} exchange={position.exchange} className="text-lg font-bold text-ink" />
          </div>
          <button ref={closeRef} type="button" onClick={onClose} aria-label="Close" className="p-1.5 rounded-interactive hover:bg-canvas text-subtle">
            <X className="w-4 h-4" aria-hidden />
          </button>
        </header>
        <div className="p-5 space-y-6">
          <Section title="Position & P&L">
            <PositionSummary position={position} />
          </Section>
          <Section title="Trades">
            <SymbolTrades clientId={clientId} symbol={position.symbol} />
          </Section>
          <Section title="Thesis">
            <ThesisPanel clientId={clientId} symbol={position.symbol} canEdit={role !== 'client'} />
          </Section>
        </div>
      </aside>
    </div>
  );
};

export default StockDetailDrawer;
