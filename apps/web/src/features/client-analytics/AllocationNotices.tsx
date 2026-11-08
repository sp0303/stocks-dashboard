import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { formatPercent, formatRupees } from '@/lib/api';
import type { Allocation, AllocationBasis, AllocationDim, AnalyticsSummary } from '@/lib/apiAnalytics';

interface Props {
  alloc: Allocation;
  dim: AllocationDim;
  basis: AllocationBasis;
  unpriced: AnalyticsSummary['unpriced'];
}

/** Unclassified share and excluded unpriced holdings (R6) are always said out loud. */
export const AllocationNotices: React.FC<Props> = ({ alloc, dim, basis, unpriced }) => (
  <>
    {alloc.unclassified.count > 0 && dim !== 'stock' && (
      <div role="status" className="mb-3 flex items-start gap-2 text-xs text-subtle border border-hairline rounded-interactive p-2.5">
        <AlertTriangle className="w-4 h-4 shrink-0" aria-hidden />
        <span>
          {alloc.unclassified.count} stock(s) have no {dim} classification ({formatPercent(alloc.unclassified.weight)}):{' '}
          {alloc.unclassified.symbols.slice(0, 8).join(', ')}
          {alloc.unclassified.symbols.length > 8 ? '…' : ''}
        </span>
      </div>
    )}
    {basis === 'current' && unpriced.count > 0 && (
      <p className="mb-3 text-xs text-subtle">
        {unpriced.count} unpriced holding(s) excluded ({formatRupees(unpriced.open_cost, 0)} at cost, R6).
      </p>
    )}
  </>
);
