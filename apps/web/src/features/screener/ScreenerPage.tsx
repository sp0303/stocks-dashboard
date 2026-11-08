import React, { useMemo } from 'react';
import { Radar } from 'lucide-react';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryStates';
import { ScreenerControls } from './ScreenerControls';
import { ScreenerTable } from './ScreenerTable';
import { MarketContextBanner } from './MarketContextBanner';
import { sectorsOf, sliceScreener, TOP_N, type SortKey } from './screenerUtils';
import { useScreenerSnapshot, useUrlParam } from './useScreener';

/** Screener: client-side top-N / sector / sort slicing of the latest research.screener_snapshots row. */
export const ScreenerPage: React.FC = () => {
  const { data, isLoading, error, refetch } = useScreenerSnapshot();
  const [topRaw, setTop] = useUrlParam('top', '20');
  const [sector, setSector] = useUrlParam('sector', '');
  const [sortRaw, setSort] = useUrlParam('sort', 'score');
  const [q, setQ] = useUrlParam('q', '');

  const top = (TOP_N as readonly number[]).includes(Number(topRaw)) ? Number(topRaw) : 20;
  const sort = (['score', 'd1', 'w1', 'm1'].includes(sortRaw) ? sortRaw : 'score') as SortKey;
  const allRows = data?.rows;
  const sectors = useMemo(() => sectorsOf(allRows ?? []), [allRows]);
  const rows = useMemo(() => sliceScreener(allRows ?? [], { sector, sort, top, q }), [allRows, sector, sort, top, q]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-ink flex items-center gap-2">
            <Radar className="w-5 h-5 text-subtle" aria-hidden /> Screener
          </h1>
          <p className="text-xs text-subtle mt-1">
            {data?.as_of ? <>Close of <strong className="text-ink">{data.data_as_of ?? data.as_of}</strong> · ranked by the Phase-1 composite · {data.count} stocks</> : 'Latest ranked snapshot'}
            {' '}· setup labels are context, not a buy call.
          </p>
        </div>
        <ScreenerControls
          sectors={sectors} sector={sector} sort={sort} top={top} q={q}
          onSector={setSector} onSort={(v) => setSort(v)} onTop={(n) => setTop(String(n))} onQ={setQ}
        />
      </div>
      {data && data.as_of && <MarketContextBanner snap={data} />}
      <div className="bg-paper border border-hairline rounded-card overflow-hidden shadow-sm">
        {isLoading && <LoadingBlock rows={6} label="Loading screener" />}
        {!isLoading && error && <ErrorBlock message={(error as Error).message} onRetry={() => refetch()} />}
        {!isLoading && !error && (allRows?.length ?? 0) === 0 && (
          <EmptyBlock icon={<Radar className="w-6 h-6" aria-hidden />} title="No screener snapshot yet" hint="Snapshots are written by the daily screener job." />
        )}
        {!isLoading && !error && (allRows?.length ?? 0) > 0 && rows.length === 0 && <EmptyBlock title="No stocks match these filters." />}
        {!isLoading && !error && rows.length > 0 && <ScreenerTable rows={rows} />}
      </div>
    </div>
  );
};

export default ScreenerPage;
