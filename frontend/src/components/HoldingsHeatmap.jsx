import { useState } from 'react'
import { api, pct, inrFull } from '../api.js'
import { Loading, ErrorBox, useAsync } from './common.jsx'

// Heatmap of every stock the selected clients hold. Two views:
//   Day      one tile per stock, coloured by that day's move (live quotes, or a past date)
//   Tracking a stock x period grid from each stock's tracking day (its oldest open lot),
//            bucketed by day / week / month so a five-year book still fits on screen.
// The API returns decimals; pct() takes percent, so every value is x100 here (R12).

const CAP = { day: 0.05, week: 0.1, month: 0.2, total: 0.5 }   // full colour at this move

function shade(r, cap) {
  if (r == null) return { background: 'var(--surface-2)', color: 'var(--faint)' }
  const p = Math.round(Math.min(Math.abs(r) / cap, 1) * 80)
  if (p < 4) return { background: 'var(--surface-2)', color: 'var(--ink)' }
  const hue = r > 0 ? 'var(--up)' : 'var(--down)'
  return { background: `color-mix(in srgb, ${hue} ${p}%, var(--surface))`, color: p > 50 ? '#fff' : 'var(--ink)' }
}

const fmt = (r) => (r == null ? '—' : pct(r * 100))

function colLabel(col, grain) {
  const d = new Date(col.last_date + 'T00:00:00')
  if (grain === 'month') return d.toLocaleDateString('en-IN', { month: 'short', year: '2-digit' })
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
}

function Legend({ cap }) {
  return (
    <div className="hm-legend" aria-hidden="true">
      <span>{fmt(-cap)}</span>
      <span className="hm-legend-bar" />
      <span>{fmt(cap)}</span>
    </div>
  )
}

function DayTiles({ tiles }) {
  return (
    <div className="hm-tiles" role="list" aria-label="Day move per holding">
      {tiles.map((t) => (
        <div key={t.symbol} role="listitem" className="hm-tile" style={shade(t.ret, CAP.day)}
          title={`${t.symbol}: ${fmt(t.ret)}${t.close != null ? ` · ₹${t.close}` : ''} · ${t.clients} client(s)${t.suspect ? ' · unusual move, check data' : ''}`}>
          <div className="hm-tile-sym">{t.symbol}{t.suspect ? ' ⚠' : ''}</div>
          <div className="hm-tile-ret tnum">{fmt(t.ret)}</div>
          <div className="hm-tile-sub tnum">{t.close != null ? `₹${t.close.toLocaleString('en-IN')}` : 'no price'} · {t.clients}c</div>
        </div>
      ))}
    </div>
  )
}

function RangeGrid({ data }) {
  const { columns, rows, grain } = data
  return (
    <div className="hm-grid-scroll">
      <table className="hm-grid" aria-label={`Returns per ${grain} since each stock's tracking day`}>
        <thead>
          <tr>
            <th className="hm-sticky">Stock · since</th>
            {columns.map((c) => <th key={c.key} title={c.key}>{colLabel(c, grain)}</th>)}
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.symbol}>
              <th className="hm-sticky" scope="row" title={`Invested ${inrFull(r.invested)} · ${r.clients} client(s)`}>
                {r.symbol}{r.suspect ? ' ⚠' : ''}<span className="hm-since">{r.start || '—'}</span>
              </th>
              {columns.map((c) => {
                const v = r.cells[c.key]
                return <td key={c.key} style={shade(v, CAP[grain])} title={`${r.symbol} ${c.key}: ${fmt(v)}`}>{v == null ? '' : (v * 100).toFixed(1)}</td>
              })}
              <td className="hm-total" style={shade(r.total, CAP.total)}>{fmt(r.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function HoldingsHeatmap({ managerId, clientIds }) {
  const [mode, setMode] = useState('day')
  const [day, setDay] = useState('')             // '' = live
  const [grain, setGrain] = useState('auto')
  const [start, setStart] = useState('')         // '' = each stock's tracking day
  const [tick, setTick] = useState(0)
  const none = clientIds && clientIds.length === 0
  const q = mode === 'day' ? { mode, day } : { mode, grain, start }
  const hm = useAsync(
    () => (none ? Promise.resolve(null) : api.holdingsHeatmap(managerId, clientIds, q)),
    [managerId, clientIds ? clientIds.join(',') : 'all', mode, day, grain, start, tick],
  )
  const d = hm.data
  const empty = none || (d && ((d.mode === 'day' && !d.tiles?.length) || (d.mode === 'range' && !d.rows?.length)))

  return (
    <div className="hm panel">
      <div className="hm-controls">
        <div className="hm-seg" role="tablist">
          <button role="tab" aria-selected={mode === 'day'} className={mode === 'day' ? 'on' : ''} onClick={() => setMode('day')}>Day</button>
          <button role="tab" aria-selected={mode === 'range'} className={mode === 'range' ? 'on' : ''} onClick={() => setMode('range')}>Since tracking day</button>
        </div>
        {mode === 'day' ? (
          <label>Date <input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
            {day && <button className="btn ghost" onClick={() => setDay('')}>Live</button>}
          </label>
        ) : (
          <>
            <label>From <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
              {start && <button className="btn ghost" onClick={() => setStart('')}>Tracking day</button>}
            </label>
            <label>Per
              <select value={grain} onChange={(e) => setGrain(e.target.value)}>
                <option value="auto">Auto</option><option value="day">Day</option>
                <option value="week">Week</option><option value="month">Month</option>
              </select>
            </label>
          </>
        )}
        <Legend cap={mode === 'day' ? CAP.day : CAP[d?.grain] || CAP.week} />
      </div>
      <p className="sub hm-note">
        {mode === 'day'
          ? (day ? `Close-to-close move on ${day}.` : 'Live move today versus the previous close.')
          : `Price move per ${d?.grain || grain}, from ${start ? start : "each stock's tracking day (its oldest lot still held)"}. This is the stock's move, not your P&L, which depends on every buy price.`}
        {d?.no_history?.length ? ` No price history: ${d.no_history.join(', ')}.` : ''}
      </p>
      {hm.loading ? <Loading what="heatmap" />
        : hm.error ? <div><ErrorBox error={hm.error} /><button className="btn ghost" onClick={() => setTick((n) => n + 1)}>Retry</button></div>
          : empty ? <div className="sub">No holdings for the selected clients{mode === 'day' && day ? ' on that date' : ''}.</div>
            : d.mode === 'day' ? <DayTiles tiles={d.tiles} /> : <RangeGrid data={d} />}
    </div>
  )
}
