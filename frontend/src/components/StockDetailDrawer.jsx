import React, { useEffect, useState } from 'react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { api, inrFull, pct } from '../api.js'
import { Stat, Loading, ErrorBox, useAsync } from './common.jsx'
import { CorporateActionsTab } from './CorporateActions.jsx'

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

const TABS = [
  { key: 'history', label: 'History' },
  { key: 'actions', label: 'Corporate Actions' },
  { key: 'remarks', label: 'Remarks' },
  { key: 'risks', label: 'Risks' },
]

export default function StockDetailDrawer({ symbol, row, onClose, onUpdate }) {
  const [tab, setTab] = useState('history')

  const up = row && row.change_pct != null && row.change_pct >= 0

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
          {row && onUpdate && <DetailsPanel row={row} onUpdate={onUpdate} />}

          <div className="drawer-tabs">
            {TABS.map((t) => (
              <button key={t.key} className={tab === t.key ? 'on' : ''} onClick={() => setTab(t.key)}>{t.label}</button>
            ))}
          </div>

          {tab === 'history' && <HistoryTab symbol={symbol} />}
          {tab === 'actions' && <CorporateActionsTab symbol={symbol} />}
          {tab === 'remarks' && (
            <NoteTab
              label="Remarks"
              placeholder="Longer notes for your own reference — thesis, catalysts, things to revisit…"
              value={row?.remarks || ''}
              rows={10}
              onSave={(remarks) => onUpdate?.({ remarks })}
            />
          )}
          {tab === 'risks' && (
            <NoteTab
              label="Risks"
              placeholder="What could go wrong — keep it short…"
              value={row?.risks || ''}
              rows={3}
              onSave={(risks) => onUpdate?.({ risks })}
            />
          )}
        </div>
      </div>
    </div>
  )
}

// The tracking fields that used to live inline in the watchlist table: when it was
// added and at what price, and the two alert triggers. Each saves on change/blur via
// onUpdate (same PATCH the inline cells used), so edits persist and re-arm alerts.
function DetailsPanel({ row, onUpdate }) {
  const today = new Date().toISOString().slice(0, 10)
  const [addedDate, setAddedDate] = useState(row.added_date || '')
  const [addedPrice, setAddedPrice] = useState(row.added_price ?? '')
  const [alertDate, setAlertDate] = useState(row.alert_date || '')
  const [alertPrice, setAlertPrice] = useState(row.alert_price ?? '')

  // Keep local inputs in sync if the row is refreshed underneath us (e.g. added_price
  // backfilled by the server, or another edit lands).
  useEffect(() => { setAddedDate(row.added_date || '') }, [row.added_date])
  useEffect(() => { setAddedPrice(row.added_price ?? '') }, [row.added_price])
  useEffect(() => { setAlertDate(row.alert_date || '') }, [row.alert_date])
  useEffect(() => { setAlertPrice(row.alert_price ?? '') }, [row.alert_price])

  const saveAddedPrice = () => {
    const cur = row.added_price ?? ''
    if (String(addedPrice) === String(cur)) return
    onUpdate({ addedPrice: addedPrice === '' ? null : Number(addedPrice) })
  }
  const saveAlertPrice = () => {
    const cur = row.alert_price ?? ''
    if (String(alertPrice) === String(cur)) return
    onUpdate({ alertPrice: alertPrice === '' ? null : Number(alertPrice) })
  }

  return (
    <div className="panel drawer-details">
      <div className="drawer-detail-grid">
        <label>
          <span className="sub">Added on</span>
          <input type="date" value={addedDate} max={today}
            onChange={(e) => { setAddedDate(e.target.value); onUpdate({ addedDate: e.target.value || null }) }} />
        </label>
        <label>
          <span className="sub">Added @ ₹</span>
          <input type="number" step="any" min="0" placeholder="—" value={addedPrice}
            onChange={(e) => setAddedPrice(e.target.value)} onBlur={saveAddedPrice}
            onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur() }} />
        </label>
        <label>
          <span className="sub">Alert date</span>
          <input type="date" value={alertDate}
            onChange={(e) => { setAlertDate(e.target.value); onUpdate({ alertDate: e.target.value || null }) }} />
        </label>
        <label>
          <span className="sub">Target ₹ {row.alert_hit && <span className="up" title="Price reached target">●</span>}</span>
          <input type="number" step="any" min="0" placeholder="—" value={alertPrice}
            title={row.alert_hit ? 'Price at/above target' : 'Target / trigger price'}
            onChange={(e) => setAlertPrice(e.target.value)} onBlur={saveAlertPrice}
            onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur() }} />
        </label>
      </div>
      {row.added_price != null && (
        <div className="sub" style={{ margin: '2px 0 0' }}>
          Since added:{' '}
          {row.diff == null ? '—' : (
            <span className={row.diff >= 0 ? 'up' : 'down'}>
              {inrFull(row.added_price)} → {row.price != null ? inrFull(row.price) : '—'} ({pct(row.diff_pct)})
            </span>
          )}
        </div>
      )}
    </div>
  )
}

function HistoryTab({ symbol }) {
  const [from, setFrom] = useState(monthsAgo(6))
  const [preset, setPreset] = useState('6M')
  const h = useAsync(() => api.history(symbol, from, '1d'), [symbol, from])

  function pick(p) { setPreset(p.key); setFrom(p.from()) }
  function onDate(e) { setPreset(null); setFrom(e.target.value) }

  const stats = h.data?.stats

  return (
    <>
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
    </>
  )
}

// Auto-saves on blur, only when the text actually changed — same pattern as the
// inline "why" cell in the watchlist table.
function NoteTab({ label, placeholder, value, rows, onSave }) {
  const [text, setText] = useState(value)
  const [saved, setSaved] = useState(true)

  return (
    <div>
      <textarea className="drawer-note" placeholder={placeholder} rows={rows} value={text}
        onChange={(e) => { setText(e.target.value); setSaved(false) }}
        onBlur={() => { if (text !== value) { onSave(text); setSaved(true) } }} />
      <div className="drawer-note-saved">{saved ? `${label} saved` : 'Unsaved changes — click away to save'}</div>
    </div>
  )
}
