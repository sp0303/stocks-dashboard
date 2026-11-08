import React from 'react';
import { AlertTriangle, RotateCw } from 'lucide-react';

/** Shared loading / error / empty states (LLD-frontend: every async component handles four states). */

export const LoadingBlock: React.FC<{ rows?: number; label?: string }> = ({ rows = 3, label = 'Loading' }) => (
  <div className="p-5 space-y-3 animate-pulse" role="status" aria-label={label}>
    {Array.from({ length: rows }, (_, i) => (
      <div key={i} className="h-8 bg-canvas rounded-interactive border border-hairline" />
    ))}
  </div>
);

export const ErrorBlock: React.FC<{ message: string; onRetry?: () => void }> = ({ message, onRetry }) => (
  <div role="alert" className="m-5 p-4 flex items-center gap-3 text-sm text-negative border border-negative/30 bg-negative/5 rounded-interactive">
    <AlertTriangle className="w-4 h-4 shrink-0" aria-hidden />
    <span className="flex-1">{message}</span>
    {onRetry && (
      <button
        type="button"
        onClick={onRetry}
        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-interactive border border-hairline bg-paper text-ink text-xs font-semibold hover:bg-canvas"
      >
        <RotateCw className="w-3 h-3" aria-hidden /> Retry
      </button>
    )}
  </div>
);

export const EmptyBlock: React.FC<{ title: string; hint?: string; icon?: React.ReactNode }> = ({ title, hint, icon }) => (
  <div className="py-12 px-5 text-center">
    {icon && <div className="flex justify-center mb-2 text-subtle">{icon}</div>}
    <div className="text-sm font-semibold text-ink">{title}</div>
    {hint && <div className="text-xs text-subtle mt-1">{hint}</div>}
  </div>
);
