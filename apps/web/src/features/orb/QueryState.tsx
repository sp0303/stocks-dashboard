import React from 'react';

interface Props {
  isLoading: boolean;
  error: unknown;
  isEmpty: boolean;
  emptyText: string;
  onRetry: () => void;
  children: React.ReactNode;
}

/** Loading / error-with-retry / empty / data, shared by every ORB card (AGENTS §5.12). */
export const QueryState: React.FC<Props> = ({ isLoading, error, isEmpty, emptyText, onRetry, children }) => {
  if (isLoading) {
    return <div className="py-6 text-center text-subtle text-sm animate-pulse" role="status">Loading…</div>;
  }
  if (error) {
    return (
      <div className="py-6 text-center text-sm text-negative" role="alert">
        Could not load this section.{' '}
        <button type="button" onClick={onRetry} className="underline font-semibold">
          Retry
        </button>
      </div>
    );
  }
  if (isEmpty) {
    return <div className="py-6 text-center text-subtle text-sm">{emptyText}</div>;
  }
  return <>{children}</>;
};
