import React from 'react';
import type { HeatmapGrain, HeatmapMode } from '@/lib/apiHeatmap';
import { CAP } from './heatShade';
import { formatPercent } from '@/lib/api';

export interface HeatmapState {
  mode: HeatmapMode;
  day: string;
  start: string;
  grain: HeatmapGrain;
}
interface Props extends HeatmapState {
  onChange: (patch: Partial<HeatmapState>) => void;
  cap: number;
}

const seg = (on: boolean) =>
  `px-3 py-1.5 text-xs font-semibold rounded-interactive ${on ? 'bg-ink text-paper' : 'text-subtle hover:text-ink'}`;
const input = 'bg-paper border border-hairline rounded-interactive px-2 py-1 text-xs text-ink';
const ghost = 'text-xs text-subtle underline hover:text-ink';

const Legend: React.FC<{ cap: number }> = ({ cap }) => (
  <span className="flex items-center gap-1.5 text-[10px] text-subtle ml-auto" aria-hidden>
    {formatPercent(-cap, 0)}
    <span className="w-24 h-2 rounded-full" style={{ background: 'linear-gradient(90deg, var(--negative), var(--canvas), var(--positive))' }} />
    {formatPercent(cap, 0)}
  </span>
);

/** Mode switch + date / grain pickers; every value lives in the URL (AGENTS §5.5). */
export const HeatmapControls: React.FC<Props> = ({ mode, day, start, grain, onChange, cap }) => (
  <div className="flex flex-wrap items-center gap-3">
    <div role="tablist" aria-label="Heatmap view" className="flex gap-1 bg-canvas border border-hairline rounded-interactive p-0.5">
      <button type="button" role="tab" aria-selected={mode === 'day'} className={seg(mode === 'day')} onClick={() => onChange({ mode: 'day' })}>Day</button>
      <button type="button" role="tab" aria-selected={mode === 'range'} className={seg(mode === 'range')} onClick={() => onChange({ mode: 'range' })}>Since tracking day</button>
    </div>
    {mode === 'day' ? (
      <label className="flex items-center gap-2 text-xs text-subtle">
        Date <input type="date" className={input} value={day} onChange={(e) => onChange({ day: e.target.value })} />
        {day && <button type="button" className={ghost} onClick={() => onChange({ day: '' })}>Latest close</button>}
      </label>
    ) : (
      <>
        <label className="flex items-center gap-2 text-xs text-subtle">
          From <input type="date" className={input} value={start} onChange={(e) => onChange({ start: e.target.value })} />
          {start && <button type="button" className={ghost} onClick={() => onChange({ start: '' })}>Tracking day</button>}
        </label>
        <label className="flex items-center gap-2 text-xs text-subtle">
          Per
          <select className={input} value={grain} onChange={(e) => onChange({ grain: e.target.value as HeatmapGrain })}>
            <option value="auto">Auto</option><option value="day">Day</option><option value="week">Week</option><option value="month">Month</option>
          </select>
        </label>
      </>
    )}
    <Legend cap={cap} />
  </div>
);

export const capFor = (mode: HeatmapMode, grain: string | null | undefined): number =>
  mode === 'day' ? CAP.day : CAP[(grain as keyof typeof CAP) ?? 'week'] ?? CAP.week;
