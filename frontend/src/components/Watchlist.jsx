import React, { useState } from 'react'
import { api } from '../api.js'
import { Loading, ErrorBox, useAsync } from './common.jsx'
import StockDetailDrawer from './StockDetailDrawer.jsx'

// scope: 'managers' | 'clients'
export default function Watchlist({ scope, id, title = 'Watchlist' }) {
  const [reload, setReload] = useState(0)
  const w = useAsync(() => api.watchlist(scope, id), [scope, id, reload])
  const [sym, setSym] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [open, setOpen] = useState(null) // watchlist row opened in the drawer

  async function add(e) {
    e.preventDefault()
    const s = sym.trim().toUpperCase()
    if (!s) return
    setBusy(true); setErr(null)
    try {
      await api.watchlistAdd(scope, id, s)
      setSym('')
      setReload((n) => n + 1)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  async function remove(s) {
    await api.watchlistRemove(scope, id, s)
    setReload((n) => n + 1)
  }

  return (
    <div>
      <h2>{title}</h2>
      <p className="sub">Click a symbol to see its price history — pick a start date or a range.</p>
      <form className="row" onSubmit={add} style={{ marginBottom: 12 }}>
        <input placeholder="Add symbol e.g. INFY" value={sym}
          onChange={(e) => setSym(e.target.value)} style={{ textTransform: 'uppercase' }} />
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
                <tr><th>Symbol</th><th className="r">Price</th><th className="r">Day change</th><th>Sector</th><th></th></tr>
              </thead>
              <tbody>
                {w.data.map((r) => (
                  <tr key={r.symbol} className="click" onClick={() => setOpen(r)}>
                    <td style={{ fontWeight: 600, color: 'var(--accent-ink)' }}>{r.symbol}</td>
                    <td className="r tnum">{r.price ?? '—'}</td>
                    <td className="r tnum">
                      {r.change_pct === null || r.change_pct === undefined ? '—' : (
                        <span className={r.change_pct >= 0 ? 'up' : 'down'}>
                          {r.change_pct >= 0 ? '+' : ''}{r.change_pct}% ({r.change >= 0 ? '+' : ''}{r.change})
                        </span>
                      )}
                    </td>
                    <td>{r.sector}</td>
                    <td className="r">
                      <button className="btn ghost" style={{ padding: '4px 10px' }}
                        onClick={(e) => { e.stopPropagation(); remove(r.symbol) }}>Remove</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </div>
  )
}
