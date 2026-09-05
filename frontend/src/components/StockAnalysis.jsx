import React, { useState } from 'react'
import { api, inr, inrFull, pct } from '../api.js'
import { Stat, Loading, ErrorBox, useAsync } from './common.jsx'

export default function StockAnalysis({ client, symbol, onBack }) {
  const s = useAsync(() => api.stock(client.id, symbol), [client.id, symbol])
  const thesis = useAsync(() => api.stockThesis(client.id, symbol), [client.id, symbol])

  return (
    <div>
      <button className="btn ghost" onClick={onBack} style={{ marginBottom: 14 }}>← Back to {client.name}</button>
      {s.loading ? <Loading what={`${symbol} analysis`} /> : s.error ? <ErrorBox error={s.error} /> : (
        <Body d={s.data} clientId={client.id} symbol={symbol} thesisData={thesis.data} onThesisUpdate={() => thesis.refetch?.()} />
      )}
    </div>
  )
}

function Body({ d, clientId, symbol, thesisData, onThesisUpdate }) {
  const held = d.current_quantity > 0
  const [thesis, setThesis] = useState(thesisData || {})
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)

  const handleThesisSave = async () => {
    setSaving(true)
    try {
      await api.saveStockThesis(clientId, symbol, thesis)
      setEditing(false)
      onThesisUpdate?.()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <div className="row" style={{ gap: 12, alignItems: 'baseline' }}>
        <h1 style={{ margin: 0 }}>{d.symbol}</h1>
        <span className="badge">{d.sector}</span>
        {d.cap && d.cap !== '—' && <span className="badge">{d.cap}</span>}
        <span className="badge">{d.asset_class}</span>
        <span className="sub" style={{ margin: 0, marginLeft: 'auto' }} >
          LTP <strong className="tnum">{d.ltp ?? '—'}</strong>
        </span>
      </div>

      {/* P&L cards */}
      <div className="cards">
        <Stat label={held ? 'Current Value' : 'Currently held'} value={held ? inr(d.market_value) : '—'} sub={held ? `${d.current_quantity} @ avg ${d.avg_cost}` : 'fully exited'} />
        <Stat label="Realized P&L" value={inr(d.realized_pnl)} tone={d.realized_pnl >= 0 ? 'up' : 'down'} />
        <Stat label="Unrealized P&L" value={d.unrealized_pnl === null ? '—' : inr(d.unrealized_pnl)} tone={(d.unrealized_pnl || 0) >= 0 ? 'up' : 'down'} />
        <Stat label="Total P&L" value={inr(d.total_pnl)} tone={d.total_pnl >= 0 ? 'up' : 'down'} />
      </div>

      {/* Position strip */}
      <div className="cards">
        <Stat label="Qty held" value={d.current_quantity} sub={held ? `avg cost ${d.avg_cost}` : ''} />
        <Stat label="Total bought" value={inr(d.total_bought_value)} sub={`${d.total_bought_qty} shares`} />
        <Stat label="Total sold" value={inr(d.total_sold_value)} sub={`${d.total_sold_qty} shares`} />
      </div>

      {/* Journey */}
      <h2>Journey</h2>
      <div className="panel" style={{ padding: 16 }}>
        <div className="row" style={{ gap: 28, flexWrap: 'wrap' }}>
          <Milestone label="First bought" date={d.first_buy_date} />
          <span className="sub" style={{ margin: 0 }}>→</span>
          <Milestone label="Last bought" date={d.last_buy_date} />
          <span className="sub" style={{ margin: 0 }}>→</span>
          <Milestone label="Last sold" date={d.last_sell_date || '—'} />
        </div>
      </div>

      {/* Timeline */}
      <h2>Transaction timeline</h2>
      <div className="panel" style={{ padding: 0 }}>
        {d.timeline.map((t, i) => (
          <div key={i} className="row" style={{
            justifyContent: 'space-between', padding: '11px 16px',
            borderBottom: i < d.timeline.length - 1 ? '1px solid var(--line)' : 'none',
          }}>
            <div className="row" style={{ gap: 12 }}>
              <span className={`badge ${t.type}`}>{t.type}</span>
              <span className="mono" style={{ color: 'var(--muted)' }}>{t.date}</span>
            </div>
            <div className="row tnum" style={{ gap: 20 }}>
              <span>{t.quantity} @ {t.price}</span>
              <strong style={{ minWidth: 90, textAlign: 'right' }}>{inrFull(t.value)}</strong>
            </div>
          </div>
        ))}
      </div>

      {/* Investment Thesis */}
      <h2 style={{ marginTop: 28, display: 'flex', gap: 12, alignItems: 'center' }}>
        Investment Thesis
        {!editing && <button className="btn sm" onClick={() => setEditing(true)}>✎ Edit</button>}
      </h2>
      <div className="panel" style={{ padding: 16 }}>
        {/* Past Orders Context */}
        {d.timeline && d.timeline.length > 0 && (
          <div style={{ marginBottom: 20, paddingBottom: 20, borderBottom: '1px solid var(--line)' }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12, color: 'var(--accent)' }}>Past Orders & Context</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, fontSize: 13 }}>
              {d.timeline.map((t, i) => (
                <div key={i} style={{ padding: 10, background: 'var(--surface-2)', borderRadius: 4 }}>
                  <div style={{ fontWeight: 600 }}>{t.type.toUpperCase()} • {t.date}</div>
                  <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 4 }}>
                    {t.quantity} @ {t.price} = {t.value}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        {editing ? (
          <ThesisForm thesis={thesis} setThesis={setThesis} onSave={handleThesisSave} onCancel={() => setEditing(false)} saving={saving} />
        ) : (
          <ThesisView thesis={thesis} />
        )}
      </div>
    </div>
  )
}

function ThesisForm({ thesis, setThesis, onSave, onCancel, saving }) {
  const fields = [
    { key: 'thesis', label: 'Thesis: Why do I believe this company will create value?', type: 'textarea' },
    { key: 'variant_view', label: 'Variant View: What do I believe that the market is missing?', type: 'textarea' },
    { key: 'catalysts', label: 'Catalysts: What could cause the market to recognise this?', type: 'textarea' },
    { key: 'time_horizon', label: 'Time Horizon', type: 'select', options: ['', '1 year', '3 years', '5 years'] },
    { key: 'key_assumptions', label: 'Key Assumptions: Revenue growth, margins, ROCE, market share, etc.', type: 'textarea' },
    { key: 'valuation', label: 'Valuation: What am I paying?', type: 'textarea' },
    { key: 'expected_return', label: 'Expected Return: What could the stock reasonably be worth?', type: 'textarea' },
    { key: 'risks', label: 'Risks: What could permanently impair the thesis?', type: 'textarea' },
    { key: 'risk_reward_ratio', label: 'Risk Reward Ratio & Portfolio Allocation %', type: 'textarea' },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {fields.map(f => (
        <div key={f.key}>
          <label style={{ display: 'block', marginBottom: 6, fontWeight: 500, fontSize: 13 }}>{f.label}</label>
          {f.type === 'textarea' ? (
            <textarea
              value={thesis[f.key] || ''}
              onChange={(e) => setThesis({ ...thesis, [f.key]: e.target.value })}
              style={{
                width: '100%', minHeight: 100, padding: 10, border: '1px solid var(--line)',
                borderRadius: 6, fontSize: 13, fontFamily: 'system-ui, -apple-system, sans-serif'
              }}
              placeholder={`Enter ${f.label.toLowerCase()}`}
            />
          ) : f.type === 'select' ? (
            <select
              value={thesis[f.key] || ''}
              onChange={(e) => setThesis({ ...thesis, [f.key]: e.target.value })}
              style={{
                width: '100%', padding: 10, border: '1px solid var(--line)',
                borderRadius: 6, fontSize: 13
              }}
            >
              {f.options.map(opt => <option key={opt} value={opt}>{opt || 'Select...'}</option>)}
            </select>
          ) : (
            <input
              type="text"
              value={thesis[f.key] || ''}
              onChange={(e) => setThesis({ ...thesis, [f.key]: e.target.value })}
              style={{
                width: '100%', padding: 10, border: '1px solid var(--line)',
                borderRadius: 6, fontSize: 13
              }}
            />
          )}
        </div>
      ))}
      <div className="row" style={{ gap: 8, marginTop: 8 }}>
        <button className="btn" onClick={onSave} disabled={saving}>{saving ? 'Saving...' : 'Save Thesis'}</button>
        <button className="btn ghost" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  )
}

function ThesisView({ thesis }) {
  if (!thesis || Object.keys(thesis).length === 0) {
    return <div style={{ color: 'var(--muted)', fontStyle: 'italic' }}>No thesis recorded yet. Click "Edit" to add one.</div>
  }

  const fields = [
    { key: 'thesis', label: 'Thesis' },
    { key: 'variant_view', label: 'Variant View' },
    { key: 'catalysts', label: 'Catalysts' },
    { key: 'time_horizon', label: 'Time Horizon' },
    { key: 'key_assumptions', label: 'Key Assumptions' },
    { key: 'valuation', label: 'Valuation' },
    { key: 'expected_return', label: 'Expected Return' },
    { key: 'risks', label: 'Risks' },
    { key: 'risk_reward_ratio', label: 'Risk Reward Ratio' },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {fields.map(f => thesis[f.key] && (
        <div key={f.key}>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6, color: 'var(--accent)' }}>{f.label}</div>
          <div style={{ fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{thesis[f.key]}</div>
        </div>
      ))}
    </div>
  )
}

function Milestone({ label, date }) {
  return (
    <div>
      <div className="label" style={{ marginBottom: 4 }}>{label}</div>
      <div className="mono" style={{ fontWeight: 600 }}>{date || '—'}</div>
    </div>
  )
}
