import React from 'react';
import { AlertTriangle } from 'lucide-react';
import type { BenchmarkTrack } from '@/lib/apiAnalytics';

/** R10 dead-ticker guard: a stale benchmark must alarm, never flatline. */
export const StaleBenchmarkBanner: React.FC<{ bench: BenchmarkTrack }> = ({ bench }) => {
  if (!bench.stale && !bench.start_backfilled) return null;
  return (
    <div role="alert" className="mb-3 flex items-start gap-2 text-xs text-negative border border-negative/30 bg-negative/5 rounded-interactive p-2.5">
      <AlertTriangle className="w-4 h-4 shrink-0" aria-hidden />
      <span>
        {bench.stale
          ? bench.last_index_date
            ? `${bench.label} data stopped on ${bench.last_index_date} (${bench.sessions_behind} sessions behind). The line ends there instead of flatlining.`
            : `No ${bench.label} data is stored for this period.`
          : `${bench.label} history starts after this portfolio's first trade; the early part of the line is missing.`}
      </span>
    </div>
  );
};
