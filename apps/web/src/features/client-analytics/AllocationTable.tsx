import React from 'react';
import { formatPercent, formatRupees } from '@/lib/api';
import type { AllocationBucket } from '@/lib/apiAnalytics';

export const AllocationTable: React.FC<{ buckets: AllocationBucket[]; caption: string }> = ({ buckets, caption }) => (
  <div className="overflow-x-auto max-h-80">
    <table className="w-full text-sm" aria-label={caption}>
      <thead className="text-[11px] uppercase text-subtle sticky top-0 bg-paper">
        <tr>
          <th scope="col" className="text-left py-2 pr-3">Bucket</th>
          <th scope="col" className="text-right py-2 pr-3">Value</th>
          <th scope="col" className="text-right py-2">Weight</th>
        </tr>
      </thead>
      <tbody>
        {buckets.map((b) => (
          <tr key={b.key} className="border-t border-hairline">
            <td className="py-1.5 pr-3 text-ink">{b.key}</td>
            <td className="py-1.5 pr-3 text-right font-mono text-ink">{formatRupees(b.value, 0)}</td>
            <td className="py-1.5 text-right font-mono text-ink">{formatPercent(b.weight)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);
