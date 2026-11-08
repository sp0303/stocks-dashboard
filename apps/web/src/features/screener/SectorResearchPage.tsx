import React, { useMemo } from 'react';
import { FlaskConical } from 'lucide-react';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryStates';
import { SectorCard } from './SectorCard';
import { MarketContextBanner } from './MarketContextBanner';
import { summariseSectors, type SectorSummary } from './screenerUtils';
import { useScreenerSnapshot, useUrlParam } from './useScreener';

type SectorSort = 'score' | 'w1' | 'm1';

function sortSectors(list: SectorSummary[], key: SectorSort): SectorSummary[] {
  const val = (s: SectorSummary) => (key === 'score' ? s.avgScore : s.avg[key]);
  return [...list].sort((a, b) => (val(b) ?? -Infinity) - (val(a) ?? -Infinity));
}

/** Sector R&D: per-sector aggregates of the latest screener snapshot (same data as the Screener). */
export const SectorResearchPage: React.FC = () => {
  const { data, isLoading, error, refetch } = useScreenerSnapshot();
  const [sortRaw, setSort] = useUrlParam('ssort', 'score');
  const sort = (['score', 'w1', 'm1'].includes(sortRaw) ? sortRaw : 'score') as SectorSort;
  const rows = data?.rows;
  const sectors = useMemo(() => sortSectors(summariseSectors(rows ?? []), sort), [rows, sort]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-ink flex items-center gap-2">
            <FlaskConical className="w-5 h-5 text-subtle" aria-hidden /> Sector R&amp;D
          </h1>
          <p className="text-xs text-subtle mt-1">
            {data?.as_of ? `Close of ${data.data_as_of ?? data.as_of} · ${sectors.length} sectors` : 'Sector momentum and leaders'}
          </p>
        </div>
        <select
          aria-label="Sort sectors"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          className="px-2.5 py-1.5 text-xs bg-canvas border border-hairline rounded-interactive text-ink"
        >
          <option value="score">Sort: avg score</option>
          <option value="w1">Sort: avg 1W</option>
          <option value="m1">Sort: avg 1M</option>
        </select>
      </div>
      {data && data.as_of && <MarketContextBanner snap={data} />}
      {isLoading && <LoadingBlock rows={4} label="Loading sectors" />}
      {!isLoading && error && <ErrorBlock message={(error as Error).message} onRetry={() => refetch()} />}
      {!isLoading && !error && sectors.length === 0 && (
        <div className="bg-paper border border-hairline rounded-card">
          <EmptyBlock icon={<FlaskConical className="w-6 h-6" aria-hidden />} title="No screener snapshot yet" />
        </div>
      )}
      {!isLoading && !error && sectors.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {sectors.map((s) => (
            <SectorCard key={s.sector} s={s} />
          ))}
        </div>
      )}
    </div>
  );
};

export default SectorResearchPage;
