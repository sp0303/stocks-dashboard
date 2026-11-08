import React, { useMemo, useState } from 'react';
import { PieChart } from 'lucide-react';
import { EChart } from '@/components/charts/EChart';
import type { AllocationBasis, AllocationDim } from '@/lib/apiAnalytics';
import { AnalyticsGate } from './AnalyticsGate';
import { AllocationNotices } from './AllocationNotices';
import { AllocationTable } from './AllocationTable';
import { Card } from './Card';
import { ConcentrationPanel } from './ConcentrationPanel';
import { Segmented } from './Segmented';
import { allocationChartOptions } from './allocationChartOptions';
import { useAnalyticsSummary } from './useAnalytics';

const BASES: { key: AllocationBasis; label: string; title: string }[] = [
  { key: 'current', label: 'Current holdings', title: 'Open holdings by market value' },
  { key: 'invested', label: 'All ever invested', title: 'Open at cost + closed stocks at peak capital' },
];
const DIMS: { key: AllocationDim; label: string }[] = [
  { key: 'sector', label: 'Sector' },
  { key: 'cap', label: 'Market cap' },
  { key: 'asset', label: 'Asset' },
  { key: 'stock', label: 'Stock' },
];

const AllocationTab: React.FC<{ clientId: string }> = ({ clientId }) => {
  const q = useAnalyticsSummary(clientId);
  const [basis, setBasis] = useState<AllocationBasis>('current');
  const [dim, setDim] = useState<AllocationDim>('sector');
  const summary = q.data?.data;
  const alloc = summary?.allocation[basis][dim];
  const options = useMemo(() => allocationChartOptions(alloc?.buckets ?? []), [alloc]);
  const controls = (
    <div className="flex flex-wrap gap-2">
      <Segmented label="Allocation basis" value={basis} options={BASES} onChange={setBasis} />
      <Segmented label="Allocation dimension" value={dim} options={DIMS} onChange={setDim} />
    </div>
  );
  return (
    <div className="space-y-4">
      <Card title="Allocation" icon={<PieChart className="w-5 h-5 text-subtle" aria-hidden />} actions={controls}>
        <AnalyticsGate
          isLoading={q.isLoading}
          error={q.error}
          onRetry={() => q.refetch()}
          empty={!alloc || alloc.buckets.length === 0}
          emptyTitle={basis === 'current' ? 'No priced open holdings' : 'No delivery positions'}
        >
          {alloc && summary && <AllocationNotices alloc={alloc} dim={dim} basis={basis} unpriced={summary.unpriced} />}
          {alloc && (
            <div className="grid lg:grid-cols-2 gap-4">
              <EChart options={options} height={Math.max(200, Math.min(alloc.buckets.length, 15) * 26)} />
              <AllocationTable buckets={alloc.buckets} caption={`Allocation by ${dim}`} />
            </div>
          )}
        </AnalyticsGate>
      </Card>
      {summary && (
        <Card title="Concentration">
          <ConcentrationPanel c={summary.concentration} />
        </Card>
      )}
    </div>
  );
};

export default AllocationTab;
