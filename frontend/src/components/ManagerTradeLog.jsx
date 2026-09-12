import React, { useState, useMemo } from 'react'
import { api, inrFull } from '../api.js'
import { Loading, ErrorBox, useAsync } from './common.jsx'

// Spreadsheet-style closed-trade journal across every account (client), mirroring the
// manager's own sheet: Account | Stock | Qty | Buy | Sell | Days | PNL | PNL% | Reason.
const COLS = [
  { key: 'account', label: 'Accounts' },
  { key: 'symbol', label: 'Stock name' },
  { key: 'quantity', label: 'Qty', r: true },
  { key: 'buy_price', label: 'Buy Price', r: true },
  { key: 'sell_price', label: 'Sell Price', r: true },
  { key: 'days', label: 'Days', r: true },
  { key: 'pnl', label: 'PNL', r: true },
  { key: 'pnl_pct', label: 'PNL%', r: true },
  { key: 'reason', label: 'Reason for buying' },
]
const PAGE = 50
const STRING_KEYS = new Set(['account', 'symbol', 'reason'])
const SORT_PRESETS = [
  { id: 'recent', label: 'Most recent', key: 'sell_date', dir: 'desc' },
  { id: 'account', label: 'Account (A–Z)', key: 'account', dir: 'asc' },
  { id: 'stock', label: 'Stock (A–Z)', key: 'symbol', dir: 'asc' },
  { id: 'pnl_hi', label: 'PNL (high → low)', key: 'pnl', dir: 'desc' },
  { id: 'pnl_lo', label: 'PNL (low → high)', key: 'pnl', dir: 'asc' },
]

export default function ManagerTradeLog({ managerId, reload }) {
  const q = useAsync(() => api.managerTradeLog(managerId), [managerId, reload])
  const [rows, setRows] = useState(null)
  const [sort, setSort] = useState({ key: 'sell_date', dir: 'desc' })
  const [fAccount, setFAccount] = useState('')
  const [fSymbol, setFSymbol] = useState('')
  const [page, setPage] = useState(0)
  const [editing, setEditing] = useState(null)   // row index being edited
  const [draft, setDraft] = useState('')

  // local working copy so inline note edits reflect immediately
  const data = rows ?? q.data
  React.useEffect(() => { if (q.data) setRows(q.data) }, [q.data])

  const accounts = useMemo(
    () => Array.from(new Set((data || []).map((r) => r.account))).sort(),
    [data]
  )

  const view = useMemo(() => {
    let v = data || []
    if (fAccount) v = v.filter((r) => r.account === fAccount)
    if (fSymbol) v = v.filter((r) => r.symbol.toLowerCase().includes(fSymbol.toLowerCase()))
    const dir = sort.dir === 'asc' ? 1 : -1
    const isStr = STRING_KEYS.has(sort.key)
    v = [...v].sort((a, b) => {
      let x = a[sort.key], y = b[sort.key]
      if (x == null) return 1
      if (y == null) return -1
      if (isStr) return String(x).trim().localeCompare(String(y).trim(), 'en', { sensitivity: 'base' }) * dir
      return (Number(x) - Number(y)) * dir
    })
    return v
  }, [data, fAccount, fSymbol, sort])

  if (q.loading && !data) return <Loading />
  if (q.error) return <ErrorBox error={q.error} />
  if (!data || !data.length) return <div className="empty">No closed trades yet across any client.</div>

  // New column: strings default A->Z (asc), numbers default high->low (desc). Same column: flip.
  const toggleSort = (key) => setSort((s) => (
    s.key === key
      ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' }
      : { key, dir: STRING_KEYS.has(key) ? 'asc' : 'desc' }
  ))
  const pages = Math.ceil(view.length / PAGE)
  const pageRows = view.slice(page * PAGE, page * PAGE + PAGE)
  const totalPnl = view.reduce((s, r) => s + (r.pnl || 0), 0)

  async function saveNote(row) {
    const note = draft.trim()
    setEditing(null)
    // optimistic: update every row sharing this buy lot (reason is per buy)
    setRows((rs) => rs.map((r) =>
      r.client_id === row.client_id && r.buy_fingerprint === row.buy_fingerprint ? { ...r, reason: note } : r
    ))
    try {
      if (row.buy_fingerprint) await api.setTradeNote(row.client_id, row.buy_fingerprint, note)
    } catch { /* keep optimistic value; a reload will resync */ }
  }

  return (
    <div>
      <div className="row" style={{ gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
        <select className="scr-select" value={fAccount} onChange={(e) => { setFAccount(e.target.value); setPage(0) }}>
          <option value="">All accounts ({accounts.length})</option>
          {accounts.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <input className="scr-input" placeholder="Filter stock…" value={fSymbol}
          onChange={(e) => { setFSymbol(e.target.value); setPage(0) }} />
        <label className="sub" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          Sort
          <select className="scr-select"
            value={(SORT_PRESETS.find((p) => p.key === sort.key && p.dir === sort.dir) || {}).id || ''}
            onChange={(e) => { const p = SORT_PRESETS.find((x) => x.id === e.target.value); if (p) { setSort({ key: p.key, dir: p.dir }); setPage(0) } }}>
            {!SORT_PRESETS.some((p) => p.key === sort.key && p.dir === sort.dir) && <option value="">Custom (column)</option>}
            {SORT_PRESETS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
        </label>
        <span className="sub" style={{ marginLeft: 'auto' }}>
          {view.length} trades · net <span className={totalPnl >= 0 ? 'up' : 'down'} style={{ fontWeight: 600 }}>{money(totalPnl)}</span>
        </span>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table className="ledger" style={{ width: '100%', fontSize: 13 }}>
          <thead>
            <tr>
              {COLS.map((c) => (
                <th key={c.key} className={`click ${c.r ? 'r' : ''}`}
                  onClick={() => c.key !== 'reason' && toggleSort(c.key === 'reason' ? 'reason' : c.key)}
                  style={{ whiteSpace: 'nowrap', cursor: c.key === 'reason' ? 'default' : 'pointer' }}>
                  {c.label}{sort.key === c.key ? (sort.dir === 'desc' ? ' ↓' : ' ↑') : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((r, i) => {
              const idx = page * PAGE + i
              return (
                <tr key={idx}>
                  <td style={{ color: 'var(--muted)', whiteSpace: 'nowrap' }}>{r.account}</td>
                  <td style={{ fontWeight: 600 }}>{r.symbol}
                    {r.cycles > 1 && <span className="sub" style={{ fontWeight: 400, color: 'var(--faint)', marginLeft: 6 }}>·{r.cycles} trades</span>}
                  </td>
                  <td className="r tnum">{fmtNum(r.quantity)}</td>
                  <td className="r tnum">₹{fmtNum(r.buy_price)}</td>
                  <td className="r tnum">₹{fmtNum(r.sell_price)}</td>
                  <td className="r tnum">{r.days}</td>
                  <td className="r tnum"><span className={r.pnl >= 0 ? 'up' : 'down'}>{money(r.pnl)}</span></td>
                  <td className="r tnum"><span className={r.pnl_pct >= 0 ? 'up' : 'down'}>{r.pnl_pct >= 0 ? '+' : ''}{r.pnl_pct}%</span></td>
                  <td style={{ minWidth: 200 }}
                    onClick={() => { if (editing !== idx) { setEditing(idx); setDraft(r.reason || '') } }}>
                    {editing === idx ? (
                      <input autoFocus className="scr-input" style={{ width: '100%', fontSize: 13 }}
                        value={draft} onChange={(e) => setDraft(e.target.value)}
                        onBlur={() => saveNote(r)}
                        onKeyDown={(e) => { if (e.key === 'Enter') saveNote(r); if (e.key === 'Escape') setEditing(null) }} />
                    ) : (
                      <span style={{ color: r.reason ? 'var(--ink)' : 'var(--faint)', cursor: 'text' }}>
                        {r.reason || 'add reason…'}
                      </span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <div className="row" style={{ gap: 8, marginTop: 10, alignItems: 'center' }}>
          <button className="btn" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Prev</button>
          <span className="sub">Page {page + 1} / {pages}</span>
          <button className="btn" disabled={page >= pages - 1} onClick={() => setPage((p) => p + 1)}>Next</button>
        </div>
      )}
    </div>
  )
}

const money = (v) => (Number(v) >= 0 ? inrFull(Number(v)) : `-${inrFull(-Number(v))}`)
const fmtNum = (v) => (v == null ? '—' : (Number.isInteger(v) ? v : Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 })))
