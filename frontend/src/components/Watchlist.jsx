import React, { useState } from 'react'
import { api } from '../api.js'
import { Loading, ErrorBox, useAsync } from './common.jsx'
import StockDetailDrawer from './StockDetailDrawer.jsx'

const today = () => new Date().toISOString().slice(0, 10)

// scope: 'managers' | 'clients'
export default function Watchlist({ scope, id, title = 'Watchlist' }) {
  const [reload, setReload] = useState(0)
  const w = useAsync(() => api.watchlist(scope, id), [scope, id, reload])
  const [sym, setSym] = useState('')
  const [checkpointDate, setCheckpointDate] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [open, setOpen] = useState(null) // watchlist row opened in the drawer
  const [editingCheckpoint, setEditingCheckpoint] = useState(null) // symbol being edited
  const [editDate, setEditDate] = useState('')

  async function add(e) {
    e.preventDefault()
    const s = sym.trim().toUpperCase()
    if (!s) return
    setBusy(true); setErr(null)
    try {
      await api.watchlistAdd(scope, id, s, checkpointDate || null)
      setSym(''); setCheckpointDate('')
      setReload((n) => n + 1)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  async function remove(s) {
    await api.watchlistRemove(scope, id, s)
    setReload((n) => n + 1)
  }

  function startEditCheckpoint(r) {
    setEditingCheckpoint(r.symbol)
    setEditDate(r.checkpoint_date || today())
  }
  async function saveCheckpoint(symbol) {
    await api.watchlistSetCheckpoint(scope, id, symbol, editDate || null)
    setEditingCheckpoint(null)
    setReload((n) => n + 1)
  }
  async function clearCheckpoint(symbol) {
    await api.watchlistSetCheckpoint(scope, id, symbol, null)
    setEditingCheckpoint(null)
    setReload((n) => n + 1)
  }

  return (
    <div>
      <h2>{title}</h2>
      <p className="sub">
        Click a symbol to see its price history. Add a checkpoint date ("watching since…") to
        track performance from that day — pick it when adding, or set/edit it any time from the row.
      </p>
      <form className="row" onSubmit={add} style={{ marginBottom: 12, flexWrap: 'wrap' }}>
        <input placeholder="Add symbol e.g. INFY" value={sym}
          onChange={(e) => setSym(e.target.value)} style={{ textTransform: 'uppercase' }} />
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, margin: 0 }}>
          Checkpoint
          <input type="date" value={checkpointDate} max={today()}
            onChange={(e) => setCheckpointDate(e.target.value)} style={{ padding: '7px 9px' }} />
        </label>
        <button className="btn" disabled={busy || !sym.trim()}>+ Add</button>
      </form>
      {err && <div className="err" style={{ marginBottom: 10 }}>⚠ {err}</div>}

      {open && <StockDetailDrawer symbol={open.symbol} row={open} onClose={() => setOpen(null)} />}

      {w.loading ? <Loading what="watchlist" /> : w.error ? <ErrorBox error={w.error} /> :
        w.data.length === 0 ? (
          <div className="empty">Nothing tracked yet. Add a symbol above.</div>
        ) : (
          <div className="panel tbl-scroll">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th><th className="r">Price</th><th className="r">Day change</th>
                  <th>Checkpoint</th><th className="r">Since checkpoint</th><th>Sector</th><th></th>
                </tr>
              </thead>
              <tbody>
                {w.data.map((r) => {
                  const editing = editingCheckpoint === r.symbol
                  const up = r.checkpoint_change_pct >= 0
                  return (
                    <tr key={r.symbol} className="click" onClick={() => !editing && setOpen(r)}>
                      <td style={{ fontWeight: 600, color: 'var(--accent-ink)' }}>{r.symbol}</td>
                      <td className="r tnum">{r.price ?? '—'}</td>
                      <td className="r tnum">
                        {r.change_pct === null || r.change_pct === undefined ? '—' : (
                          <span className={r.change_pct >= 0 ? 'up' : 'down'}>
                            {r.change_pct >= 0 ? '+' : ''}{r.change_pct}% ({r.change >= 0 ? '+' : ''}{r.change})
                          </span>
                        )}
                      </td>
                      <td onClick={(e) => e.stopPropagation()}>
                        {editing ? (
                          <div className="row" style={{ gap: 6, flexWrap: 'nowrap' }}>
                            <input type="date" value={editDate} max={today()}
                              onChange={(e) => setEditDate(e.target.value)} style={{ padding: '4px 6px', fontSize: 12 }} />
                            <button className="btn" style={{ padding: '4px 8px' }} onClick={() => saveCheckpoint(r.symbol)}>Save</button>
                            {r.checkpoint_date && (
                              <button className="btn ghost" style={{ padding: '4px 8px' }} onClick={() => clearCheckpoint(r.symbol)}>Clear</button>
                            )}
                            <button className="btn ghost" style={{ padding: '4px 8px' }} onClick={() => setEditingCheckpoint(null)}>✕</button>
                          </div>
                        ) : r.checkpoint_date ? (
                          <span className="mono click" onClick={() => startEditCheckpoint(r)} title="Click to edit">
                            {r.checkpoint_date}
                          </span>
                        ) : (
                          <button type="button" className="tag-add" onClick={() => startEditCheckpoint(r)}>+ Set date</button>
                        )}
                      </td>
                      <td className="r tnum">
                        {r.checkpoint_change_pct === null || r.checkpoint_change_pct === undefined ? '—' : (
                          <span className={up ? 'up' : 'down'}>
                            {up ? '+' : ''}{r.checkpoint_change_pct}%
                            {r.checkpoint_price != null && <span className="sub" style={{ margin: 0 }}> (from {r.checkpoint_price})</span>}
                          </span>
                        )}
                      </td>
                      <td>{r.sector}</td>
                      <td className="r">
                        <button className="btn ghost" style={{ padding: '4px 10px' }}
                          onClick={(e) => { e.stopPropagation(); remove(r.symbol) }}>Remove</button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
    </div>
  )
}
