import React from 'react';
import { BarChart3 } from 'lucide-react';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryStates';
import { NotComputedError } from '@/lib/apiAnalytics';

interface Props {
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
  empty?: boolean;
  emptyTitle?: string;
  emptyHint?: string;
  children: React.ReactNode;
}

/** The four async states (LLD-frontend §5.12): loading, empty (incl. not yet computed), error + retry, data. */
export const AnalyticsGate: React.FC<Props> = ({ isLoading, error, onRetry, empty, emptyTitle, emptyHint, children }) => {
  if (isLoading) return <LoadingBlock rows={4} label="Loading analytics" />;
  if (error instanceof NotComputedError) {
    return (
      <EmptyBlock
        icon={<BarChart3 className="w-6 h-6" aria-hidden />}
        title="Analytics not computed yet"
        hint="They are rebuilt by the portfolio worker after each upload or nightly recompute."
      />
    );
  }
  if (error) return <ErrorBlock message={error instanceof Error ? error.message : 'Failed to load analytics'} onRetry={onRetry} />;
  if (empty) return <EmptyBlock icon={<BarChart3 className="w-6 h-6" aria-hidden />} title={emptyTitle ?? 'Nothing to show'} hint={emptyHint} />;
  return <>{children}</>;
};
