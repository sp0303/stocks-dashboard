import React, { useState, useEffect } from 'react'
import { api, CA_TYPES } from '../api.js'
import { Loading, ErrorBox, useAsync } from './common.jsx'

// A small coloured tag naming a corporate-action type.
export function CATag({ type }) {
  const meta = CA_TYPES[type] || { label: type, tone: '' }
  return <span className={`ca-tag ${meta.tone}`}>{meta.label}</span>
}

const fmtDate = (d) => (d ? d : '—')
const fmtMult = (a) =>
  a.type === 'SPLIT' || a.type === 'BONUS'
    ? `×${Number(a.qty_multiplier).toFixed(a.qty_multiplier % 1 ? 2 : 0)}`
    : a.type === 'DIVIDEND' && a.amount_per_share != null
      ? `₹${a.amount_per_share}/sh`
      : '—'

// A table of corporate actions, sortable by column. `dense` drops the symbol column
// (used in the per-symbol drawer); `pageSize` (e.g. 10) paginates client-side.
export function CATable({ rows, dense, pageSize }) {
  const [sort, setSort] = useState({ key: 'ex_date', dir: 'desc' })
  const [page, setPage] = useState(0)
  // reset to the first page whenever the sort or the underlying data changes
  useEffect(() => { setPage(0) }, [sort, rows])

  if (!rows || !rows.length) return <div className="empty">No corporate actions on record.</div>

  const cols = [
    { key: 'ex_date', label: 'Ex-date' },
    { key: 'type', label: 'Type' },
    ...(dense ? [] : [{ key: 'symbol', label: 'Symbol' }]),
    { key: 'qty_multiplier', label: 'Effect', r: true },
    { key: 'subject', label: 'Detail' },
  ]
  function toggleSort(key) {
    setSort((cur) => (cur.key === key ? { key, dir: cur.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }))
  }
  const sorted = [...rows].sort((a, b) => {
    let av = a[sort.key], bv = b[sort.key]
    if (sort.key === 'qty_multiplier') { av = a.amount_per_share ?? a.qty_multiplier; bv = b.amount_per_share ?? b.qty_multiplier }
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    if (typeof av === 'string') return sort.dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av)
    return sort.dir === 'asc' ? av - bv : bv - av
  })
  const totalPages = pageSize ? Math.ceil(sorted.length / pageSize) : 1
  const paged = pageSize ? sorted.slice(page * pageSize, page * pageSize + pageSize) : sorted

  return (
    <>
      <div className="ca-table-wrap">
        <table className="ca-table">
          <thead>
            <tr>
              {cols.map((c) => (
                <th key={c.key} className={`${c.r ? 'r ' : ''}click`} onClick={() => toggleSort(c.key)}>
                  {c.label}{sort.key === c.key ? (sort.dir === 'desc' ? ' ▾' : ' ▴') : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paged.map((a, i) => (
              <tr key={a.key || i}>
                <td className="tnum">{fmtDate(a.ex_date)}</td>
                <td><CATag type={a.type} /></td>
                {!dense && <td style={{ fontWeight: 600 }}>{a.symbol}</td>}
                <td className="r tnum">{fmtMult(a)}</td>
                <td className="sub" style={{ maxWidth: 320 }}>{a.subject}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <div className="row" style={{ justifyContent: 'center', marginTop: 12, gap: 8 }}>
          <button className="btn ghost" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>← Prev</button>
          <span className="sub" style={{ margin: 0 }}>Page {page + 1} of {totalPages}</span>
          <button className="btn ghost" disabled={page >= totalPages - 1} onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}>Next →</button>
        </div>
      )}
    </>
  )
}

// Drawer tab: corporate actions for a single symbol.
export function CorporateActionsTab({ symbol }) {
  const s = useAsync(() => api.corpActions(symbol), [symbol])
  if (s.loading) return <Loading what="corporate actions" />
  if (s.error) return <ErrorBox error={s.error} />
  const rows = [...s.data].sort((a, b) => (b.ex_date || '').localeCompare(a.ex_date || ''))
  return (
    <>
      <p className="sub" style={{ marginTop: 0 }}>
        Splits & bonuses are applied automatically to your held quantity on the ex-date.
      </p>
      <CATable rows={rows} dense />
    </>
  )
}

// Client-level feed: every corporate action across the client's holdings, with a refresh.
export function CorporateActionsFeed({ client }) {
  const [reload, setReload] = useState(0)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const s = useAsync(() => api.clientCorpActions(client.id), [client.id, reload])

  async function refresh() {
    setBusy(true); setMsg(null)
    try {
      const r = await api.clientCorpActionsRefresh(client.id)
      setMsg(`Fetched ${r.fetched} actions across ${r.symbols} symbols (${r.saved} new).`)
      setReload((n) => n + 1)
    } catch (e) {
      setMsg(`Refresh failed: ${e.message}`)
    } finally {
      setBusy(false)
    }
  }

  const rows = s.data || []
  const qtyChanging = rows.filter((a) => a.type === 'SPLIT' || a.type === 'BONUS')

  return (
    <div>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div className="sub" style={{ margin: 0 }}>
          {rows.length} actions on record · {qtyChanging.length} split/bonus events affect share counts
        </div>
        <button className="btn" onClick={refresh} disabled={busy}>
          {busy ? 'Refreshing…' : '↻ Refresh from NSE'}
        </button>
      </div>
      {msg && <div className="sub" style={{ marginBottom: 10 }}>{msg}</div>}
      {s.loading ? <Loading what="corporate actions" /> : s.error ? <ErrorBox error={s.error} /> : (
        <CATable rows={rows} pageSize={10} />
      )}
    </div>
  )
}

// Admin control: market-wide coverage stats + refresh / backfill triggers with progress.
export function CorporateActionsAdmin() {
  const [reload, setReload] = useState(0)
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState(null)
  const s = useAsync(() => api.corpActionsCoverage(), [reload])

  async function run(kind) {
    setBusy(kind); setMsg(null)
    try {
      if (kind === 'portfolio') {
        const r = await api.corpActionsRefresh()
        setMsg(`Portfolio refresh: ${r.fetched} actions across ${r.symbols} symbols (${r.saved} new).`)
      } else {
        await api.corpActionsRefreshAll()
        setMsg('Market-wide backfill started — this runs in the background; refresh coverage to watch progress.')
      }
      setReload((n) => n + 1)
    } catch (e) {
      setMsg(`Failed: ${e.message}`)
    } finally {
      setBusy('')
    }
  }

  const cov = s.data
  const bf = cov?.backfill

  return (
    <div className="panel" style={{ padding: 16 }}>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
        <div>
          <div style={{ fontWeight: 700 }}>Corporate actions</div>
          <div className="sub" style={{ margin: '2px 0 0' }}>
            {s.loading ? 'Loading coverage…' : s.error ? 'Coverage unavailable' :
              `${cov.total.toLocaleString()} actions stored · ${cov.symbols.toLocaleString()} symbols`}
          </div>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn" onClick={() => run('portfolio')} disabled={!!busy}>
            {busy === 'portfolio' ? 'Refreshing…' : 'Refresh held symbols'}
          </button>
          <button className="btn" onClick={() => run('all')} disabled={!!busy || bf?.running}>
            {bf?.running ? 'Backfill running…' : 'Backfill all NSE'}
          </button>
          <button className="btn ghost" onClick={() => setReload((n) => n + 1)} disabled={!!busy}>↻</button>
        </div>
      </div>
      {bf && bf.total > 0 && (
        <div style={{ marginTop: 12 }}>
          <div className="ca-progress"><div className="ca-progress-bar" style={{ width: `${Math.round((bf.done / bf.total) * 100)}%` }} /></div>
          <div className="sub" style={{ margin: '4px 0 0' }}>
            {bf.running ? 'Backfilling' : 'Last backfill'}: {bf.done}/{bf.total} symbols · {bf.saved} actions saved
          </div>
        </div>
      )}
      {msg && <div className="sub" style={{ marginTop: 10 }}>{msg}</div>}
    </div>
  )
}
