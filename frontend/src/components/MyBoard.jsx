import React, { useState } from 'react'
import { api, inr, pct } from '../api.js'
import { Loading, ErrorBox, useAsync } from './common.jsx'
import './MyBoard.css'

const COLUMNS = [
  { key: 'watching', title: 'Watching', hint: 'Idea — not yet entered' },
  { key: 'holding', title: 'Holding', hint: 'Position is on' },
  { key: 'exit', title: 'Exit', hint: 'Closed out' },
]

// Actual P&L once a real entry price exists (from the Holding transition); falls
// back to the planned entry_price so a card still shows something before that.
function pnlPct(item) {
  const base = item.entered_price ?? item.entry_price
  const cur = item.status === 'exit' ? (item.exited_price ?? item.price) : item.price
  if (base == null || cur == null) return null
  return ((cur - base) / base) * 100
}

export default function MyBoard({ managerId }) {
  const [reload, setReload] = useState(0)
  const b = useAsync(() => api.board(managerId), [managerId, reload])
  const [err, setErr] = useState(null)
  const [adding, setAdding] = useState(false)

  function refresh() { setReload((n) => n + 1) }

  async function run(fn) {
    setErr(null)
    try { await fn() } catch (e) { setErr(e.message) }
    refresh()
  }

  if (b.loading) return <Loading what="board" />
  if (b.error) return <ErrorBox error={b.error} />
  const items = b.data || []

  return (
    <div className="myboard">
      <div className="myboard-head">
        <h2>MyBoard</h2>
        <button className="myboard-add-btn" onClick={() => setAdding(true)}>+ Add stock</button>
      </div>
      {err && <div className="warn-banner">{err}</div>}
      {adding && (
        <AddCard
          onCancel={() => setAdding(false)}
          onSave={(vals) => run(async () => {
            await api.boardAdd(managerId, vals)
            setAdding(false)
          })}
        />
      )}
      <div className="myboard-cols">
        {COLUMNS.map((col) => (
          <div key={col.key} className="myboard-col">
            <div className="myboard-col-head">
              <span className="myboard-col-title">{col.title}</span>
              <span className="myboard-col-count">{items.filter((i) => i.status === col.key).length}</span>
            </div>
            <div className="myboard-col-hint">{col.hint}</div>
            <div className="myboard-col-body">
              {items.filter((i) => i.status === col.key).map((item) => (
                <Card
                  key={item.id}
                  item={item}
                  onMove={(status) => run(() => api.boardUpdate(managerId, item.id, { status }))}
                  onEditWhy={(why) => run(() => api.boardUpdate(managerId, item.id, { why }))}
                  onEditPlan={(patch) => run(() => api.boardUpdate(managerId, item.id, patch))}
                  onRemove={() => {
                    if (window.confirm(`Remove ${item.symbol} from the board?`)) run(() => api.boardRemove(managerId, item.id))
                  }}
                />
              ))}
              {items.filter((i) => i.status === col.key).length === 0 && (
                <div className="myboard-empty">Nothing here</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function AddCard({ onSave, onCancel }) {
  const [symbol, setSymbol] = useState('')
  const [entryPrice, setEntryPrice] = useState('')
  const [exitPrice, setExitPrice] = useState('')
  const [why, setWhy] = useState('')
  const [busy, setBusy] = useState(false)

  async function save() {
    if (!symbol.trim()) return
    setBusy(true)
    await onSave({
      symbol: symbol.trim().toUpperCase(),
      entryPrice: entryPrice ? Number(entryPrice) : undefined,
      exitPrice: exitPrice ? Number(exitPrice) : undefined,
      why: why.trim() || undefined,
    })
    setBusy(false)
  }

  return (
    <div className="myboard-addform">
      <input placeholder="Symbol (e.g. TCS)" value={symbol} onChange={(e) => setSymbol(e.target.value)} autoFocus />
      <input placeholder="Entry price" type="number" value={entryPrice} onChange={(e) => setEntryPrice(e.target.value)} />
      <input placeholder="Exit price (target)" type="number" value={exitPrice} onChange={(e) => setExitPrice(e.target.value)} />
      <input placeholder="Why? (thesis)" value={why} onChange={(e) => setWhy(e.target.value)} className="myboard-why-input" />
      <button onClick={save} disabled={busy || !symbol.trim()}>{busy ? 'Adding…' : 'Add'}</button>
      <button onClick={onCancel} className="myboard-cancel">Cancel</button>
    </div>
  )
}

function Card({ item, onMove, onEditWhy, onEditPlan, onRemove }) {
  const [why, setWhy] = useState(item.why || '')
  const [editingPlan, setEditingPlan] = useState(false)
  const [entryPrice, setEntryPrice] = useState(item.entry_price ?? '')
  const [exitPrice, setExitPrice] = useState(item.exit_price ?? '')
  const pnl = pnlPct(item)

  function saveWhy() { if (why !== (item.why || '')) onEditWhy(why) }
  function savePlan() {
    onEditPlan({
      entryPrice: entryPrice === '' ? undefined : Number(entryPrice),
      exitPrice: exitPrice === '' ? undefined : Number(exitPrice),
    })
    setEditingPlan(false)
  }

  return (
    <div className="myboard-card">
      <div className="myboard-card-top">
        <span className="myboard-symbol">{item.symbol}</span>
        <span className="myboard-price">{item.price != null ? inr(item.price) : '—'}</span>
        <button className="myboard-remove" title="Remove" onClick={onRemove}>×</button>
      </div>

      {item.status !== 'watching' && pnl != null && (
        <div className={`myboard-pnl ${pnl >= 0 ? 'up' : 'down'}`}>{pct(pnl)} since entry</div>
      )}

      {editingPlan ? (
        <div className="myboard-plan-edit">
          <input type="number" placeholder="Entry" value={entryPrice} onChange={(e) => setEntryPrice(e.target.value)} />
          <span>→</span>
          <input type="number" placeholder="Exit" value={exitPrice} onChange={(e) => setExitPrice(e.target.value)} />
          <button onClick={savePlan}>✓</button>
        </div>
      ) : (
        <div className="myboard-plan" onClick={() => setEditingPlan(true)} title="Click to edit">
          Entry {item.entry_price != null ? inr(item.entry_price) : '—'} → Exit {item.exit_price != null ? inr(item.exit_price) : '—'}
        </div>
      )}

      {item.status !== 'watching' && (
        <div className="myboard-actual">
          {item.entered_price != null && <span>Entered {inr(item.entered_price)} on {item.entered_at}</span>}
          {item.status === 'exit' && item.exited_price != null && <span> · Exited {inr(item.exited_price)} on {item.exited_at}</span>}
        </div>
      )}

      <textarea
        className="myboard-why"
        placeholder="Why? (thesis)"
        value={why}
        onChange={(e) => setWhy(e.target.value)}
        onBlur={saveWhy}
        rows={2}
      />

      <div className="myboard-actions">
        {item.status === 'watching' && <button onClick={() => onMove('holding')}>Move to Holding →</button>}
        {item.status === 'holding' && (
          <>
            <button onClick={() => onMove('watching')}>← Back to Watching</button>
            <button onClick={() => onMove('exit')}>Move to Exit →</button>
          </>
        )}
        {item.status === 'exit' && <button onClick={() => onMove('holding')}>← Reopen to Holding</button>}
      </div>
    </div>
  )
}
