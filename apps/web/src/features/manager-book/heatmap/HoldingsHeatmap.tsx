import React, { useMemo } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryStates';
import { fetchHeatmap, type HeatmapGrain, type HeatmapMode, type HeatmapResponse } from '@/lib/apiHeatmap';
import { ClientMultiSelect } from '../ClientMultiSelect';
import { bookKey, useBookSummary, useUrlParam } from '../useBook';
import { DayTiles } from './DayTiles';
import { HeatmapControls, capFor, type HeatmapState } from './HeatmapControls';
import { RangeGrid } from './RangeGrid';

function note(d: HeatmapResponse | undefined, s: HeatmapState): string {
  const base = s.mode === 'day'
    ? `Close-to-close move on ${d?.day ?? (s.day || 'the latest close')}.`
    : `Price move per ${d?.grain ?? s.grain}, from ${s.start || "each stock's tracking day (its oldest lot still held)"}. This is the stock's move, not your P&L, which depends on every buy price.`;
  return d?.no_history.length ? `${base} No price history: ${d.no_history.join(', ')}.` : base;
}

const isEmpty = (d: HeatmapResponse) => (d.mode === 'day' ? d.tiles.length === 0 : d.rows.length === 0);

/** v1 My Board heatmap: every stock the selected clients hold (selection shared with Holdings, `hc`). */
export const HoldingsHeatmap: React.FC<{ managerId: string }> = ({ managerId }) => {
  const roster = useBookSummary(managerId);
  const [hc, setHc] = useUrlParam('hc');
  const [mode, setMode] = useUrlParam('hm', 'day');
  const [day, setDay] = useUrlParam('hd');
  const [start, setStart] = useUrlParam('hs');
  const [grain, setGrain] = useUrlParam('hg', 'auto');
  const s: HeatmapState = { mode: mode as HeatmapMode, day, start, grain: grain as HeatmapGrain };
  const selected = useMemo(() => new Set(hc ? hc.split(',') : []), [hc]);
  const clientIds = useMemo(() => [...selected].sort(), [selected]);
  const q = useQuery({
    queryKey: bookKey(managerId, `heatmap:${s.mode}:${clientIds.join(',')}:${s.mode === 'day' ? day : `${start}:${grain}`}`),
    queryFn: () => fetchHeatmap(managerId, { ...s, clientIds }),
    placeholderData: keepPreviousData,
  });
  const onChange = (p: Partial<HeatmapState>) => {
    if (p.mode !== undefined) setMode(p.mode);
    if (p.day !== undefined) setDay(p.day);
    if (p.start !== undefined) setStart(p.start);
    if (p.grain !== undefined) setGrain(p.grain);
  };
  const d = q.data && q.data.mode === s.mode ? q.data : undefined;
  return (
    <div className="bg-paper border border-hairline rounded-card shadow-sm p-5 space-y-4">
      <h2 className="text-base font-semibold text-ink">Heatmap of held stocks</h2>
      <ClientMultiSelect clients={roster.data?.clients ?? []} selected={selected} onChange={(n) => setHc([...n].join(','))} />
      <HeatmapControls {...s} onChange={onChange} cap={capFor(s.mode, d?.grain)} />
      <p className="text-xs text-subtle">{note(d, s)}</p>
      {q.isLoading || (q.isFetching && !d) ? <LoadingBlock rows={4} label="Loading heatmap" />
        : q.isError ? <ErrorBlock message="Could not load the heatmap." onRetry={() => q.refetch()} />
          : !d || isEmpty(d) ? <EmptyBlock title="No holdings" hint={selected.size ? 'The selected clients hold nothing.' : 'No client holds a position.'} />
            : d.mode === 'day' ? <DayTiles tiles={d.tiles} /> : <RangeGrid data={d} />}
    </div>
  );
};
