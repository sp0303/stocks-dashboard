import React, { useState } from 'react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { api } from '../api.js'
import { Stat, Loading, ErrorBox, useAsync } from './common.jsx'

// ISO date `n` months ago
function monthsAgo(n) {
  const d = new Date()
  d.setMonth(d.getMonth() - n)
  return d.toISOString().slice(0, 10)
}
const PRESETS = [
  { key: '1M', from: () => monthsAgo(1) },
  { key: '3M', from: () => monthsAgo(3) },
  { key: '6M', from: () => monthsAgo(6) },
  { key: '1Y', from: () => monthsAgo(12) },
  { key: '3Y', from: () => monthsAgo(36) },
]

export default function StockDetailDrawer({ symbol, row, onClose }) {
  const [from, setFrom] = useState(monthsAgo(6))
  const [preset, setPreset] = useState('6M')
  const h = useAsync(() => api.history(symbol, from, '1d'), [symbol, from])

  function pick(p) { setPreset(p.key); setFrom(p.from()) }
  function onDate(e) { setPreset(null); setFrom(e.target.value) }

  const up = row && row.change_pct != null && row.change_pct >= 0
  const stats = h.data?.stats

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <div>
            <div style={{ fontWeight: 700, fontSize: 18 }}>{symbol}</div>
            <div className="sub" style={{ margin: 0 }}>{row?.sector || ''}</div>
          </div>
          <div className="row" style={{ gap: 14 }}>
            {row && (
              <div style={{ textAlign: 'right' }}>
                <div className="tnum" style={{ fontWeight: 700, fontSize: 18 }}>{row.price ?? '—'}</div>
                {row.change_pct != null && (
                  <div className={up ? 'up' : 'down'} style={{ fontSize: 13 }}>
                    {up ? '+' : ''}{row.change_pct}% ({up ? '+' : ''}{row.change})
                  </div>
                )}
              </div>
            )}
            <button className="close" onClick={onClose} aria-label="Close">×</button>
          </div>
        </div>

        <div className="drawer-body">
          <div className="presets">
            {PRESETS.map((p) => (
              <button key={p.key} className={preset === p.key ? 'on' : ''} onClick={() => pick(p)}>{p.key}</button>
            ))}
            <label style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
              From
              <input type="date" value={from} max={new Date().toISOString().slice(0, 10)} onChange={onDate}
                style={{ padding: '5px 8px' }} />
            </label>
          </div>

          {h.loading ? <Loading what="price history" /> : h.error ? <ErrorBox error={h.error} /> :
            !h.data.points.length ? (
              <div className="empty">No price history available for this range.</div>
            ) : (
              <>
                <div className="panel" style={{ padding: 14, marginBottom: 16 }}>
                  <ResponsiveContainer width="100%" height={260}>
                    <AreaChart data={h.data.points} margin={{ top: 6, right: 10, bottom: 0, left: 6 }}>
                      <defs>
                        <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.35} />
                          <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
                      <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--muted)' }} minTickGap={44} />
                      <YAxis domain={['auto', 'auto']} tick={{ fontSize: 10, fill: 'var(--muted)' }} width={52}
                        tickFormatter={(v) => '₹' + v} />
                      <Tooltip formatter={(v) => ['₹' + v, 'Close']} labelStyle={{ color: '#111' }} />
                      <Area type="monotone" dataKey="close" stroke="var(--accent)" strokeWidth={2} fill="url(#g)" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>

                {stats && (
                  <div className="cards">
                    <Stat label="Period change" value={`${stats.change_pct >= 0 ? '+' : ''}${stats.change_pct}%`}
                      tone={stats.change_pct >= 0 ? 'up' : 'down'} sub={`${stats.start_close} → ${stats.end_close}`} />
                    <Stat label="Period high" value={`₹${stats.period_high}`} />
                    <Stat label="Period low" value={`₹${stats.period_low}`} />
                  </div>
                )}
                <p className="sub" style={{ marginTop: 10 }}>
                  {h.data.points.length} trading days · {from} → today · daily close
                </p>
              </>
            )}
        </div>
      </div>
    </div>
  )
}
