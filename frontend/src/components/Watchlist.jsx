import React, { useEffect, useState } from 'react'
import { api, inrFull, pct } from '../api.js'
import { Loading, ErrorBox, useAsync } from './common.jsx'
import StockDetailDrawer from './StockDetailDrawer.jsx'

// Common sectors offered as datalist suggestions when overriding a symbol's
// classification. Free text is still allowed — this is just for convenience.
export const SECTORS = [
  'Financial Services', 'Information Technology', 'Healthcare / Pharma', 'FMCG',
  'Automobile', 'Capital Goods', 'Metals & Mining', 'Energy / Oil & Gas',
  'Consumer Durables', 'Consumer Services', 'Chemicals', 'Cement & Building Materials',
  'Power / Utilities', 'Realty', 'Infrastructure', 'Telecommunication', 'Media',
  'Index / ETF',
]

const MAX_WATCHLISTS = 10

// scope: 'managers' | 'clients'
export default function Watchlist({ scope, id, title = 'Watchlist' }) {
  const isManager = scope === 'managers'
  // Named lists (managers only). Clients keep a single default list — no tab bar.
  const [lists, setLists] = useState(isManager ? null : [])
  const [activeId, setActiveId] = useState(null)
  const [listErr, setListErr] = useState(null)

  async function refreshLists(preferId) {
    if (!isManager) return
    try {
      const ls = await api.watchlistLists(scope, id)
      setLists(ls)
      setActiveId((cur) => {
        const want = preferId || cur
        return want && ls.some((l) => l.id === want) ? want : (ls[0]?.id || null)
      })
    } catch (e) { setListErr(e.message) }
  }

  useEffect(() => { refreshLists() }, [scope, id]) // eslint-disable-line react-hooks/exhaustive-deps

  const wlId = isManager ? activeId : undefined
  const ready = !isManager || !!activeId

  const [reload, setReload] = useState(0)
  const w = useAsync(() => (ready ? api.watchlist(scope, id, wlId) : Promise.resolve([])), [scope, id, wlId, reload, ready])
  const today = new Date().toISOString().slice(0, 10)
  const [sym, setSym] = useState('')
  const [why, setWhy] = useState('')
  const [sector, setSector] = useState('')
  const [addedDate, setAddedDate] = useState(today)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [open, setOpen] = useState(null) // watchlist row opened in the drawer
  const [sortKey, setSortKey] = useState('symbol') // 'symbol' | 'price'
  const [sortDir, setSortDir] = useState('asc')     // 'asc' | 'desc'
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 10

  function toggleSort(key) {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir('asc') }
  }
  const sortInd = (key) => (sortKey === key ? (sortDir === 'asc' ? ' ▲' : ' ▼') : '')

  // Reset to the first page when the list, sort, or symbol count changes.
  useEffect(() => { setPage(1) }, [wlId, sortKey, sortDir, w.data?.length])

  async function add(e) {
    e.preventDefault()
    const s = sym.trim().toUpperCase()
    if (!s) return
    setBusy(true); setErr(null)
    try {
      await api.watchlistAdd(scope, id, s, { why: why.trim(), addedDate, sector: sector.trim() }, wlId)
      setSym(''); setWhy(''); setSector(''); setAddedDate(today)
      setReload((n) => n + 1)
      refreshLists(activeId)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  async function remove(s) {
    await api.watchlistRemove(scope, id, s, wlId)
    setReload((n) => n + 1)
    refreshLists(activeId)
  }

  async function updateEntry(s, patch) {
    await api.watchlistUpdate(scope, id, s, patch, wlId)
    setReload((n) => n + 1)
  }

  // Keep the drawer's row in sync after an inline edit so the details panel reflects saves.
  useEffect(() => {
    if (open) {
      const fresh = (w.data || []).find((r) => r.symbol === open.symbol)
      if (fresh && fresh !== open) setOpen(fresh)
    }
  }, [w.data]) // eslint-disable-line react-hooks/exhaustive-deps

  // Sort (name or price; nulls always last) then paginate at PAGE_SIZE per page.
  const sorted = [...(w.data || [])].sort((a, b) => {
    let cmp
    if (sortKey === 'price') {
      const av = a.price, bv = b.price
      if (av == null && bv == null) cmp = 0
      else if (av == null) return 1
      else if (bv == null) return -1
      else cmp = av - bv
    } else {
      cmp = String(a.symbol).localeCompare(String(b.symbol))
    }
    return sortDir === 'asc' ? cmp : -cmp
  })
  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE))
  const curPage = Math.min(page, totalPages)
  const pageRows = sorted.slice((curPage - 1) * PAGE_SIZE, curPage * PAGE_SIZE)

  return (
    <div>
      <h2>{title}</h2>
      <p className="sub">Click a symbol to open its detail panel — price history, added-on / alert settings, and notes.</p>
      <AlertsBar />

      {isManager && (
        <WatchlistTabs
          lists={lists} activeId={activeId} onSelect={setActiveId} err={listErr}
          onCreate={async () => {
            setListErr(null)
            try {
              const n = (lists?.length || 0) + 1
              const created = await api.watchlistListCreate(scope, id, `Watchlist ${n}`)
              await refreshLists(created.id)
            } catch (e) { setListErr(e.message) }
          }}
          onRename={async (wid, name) => {
            setListErr(null)
            try { await api.watchlistListRename(scope, id, wid, name); await refreshLists(wid) }
            catch (e) { setListErr(e.message) }
          }}
          onDelete={async (wid) => {
            setListErr(null)
            try { await api.watchlistListDelete(scope, id, wid); await refreshLists() }
            catch (e) { setListErr(e.message) }
          }}
        />
      )}

      <form className="row" onSubmit={add} style={{ marginBottom: 12 }}>
        <input placeholder="Add symbol e.g. INFY" value={sym}
          onChange={(e) => setSym(e.target.value)} style={{ textTransform: 'uppercase' }} />
        <input placeholder="Why? (optional)" value={why}
          onChange={(e) => setWhy(e.target.value)} style={{ minWidth: 180 }} />
        <label className="row" style={{ gap: 6 }}>
          <span className="sub" style={{ margin: 0 }}>Added on</span>
          <input type="date" value={addedDate} max={today} title="Added on — pick a past date to record it at that day's closing price"
            onChange={(e) => setAddedDate(e.target.value || today)} />
        </label>
        <select value={sector} title="Override the auto-detected sector (optional)"
          onChange={(e) => setSector(e.target.value)}>
          <option value="">Sector — auto</option>
          {SECTORS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <button className="btn" disabled={busy || !sym.trim() || !ready}>+ Add</button>
      </form>
      {err && <div className="err" style={{ marginBottom: 10 }}>⚠ {err}</div>}

      {open && (
        <StockDetailDrawer symbol={open.symbol} row={open} onClose={() => setOpen(null)}
          onUpdate={(patch) => updateEntry(open.symbol, patch)} />
      )}

      {w.loading ? <Loading what="watchlist" /> : w.error ? <ErrorBox error={w.error} /> :
        w.data.length === 0 ? (
          <div className="empty">Nothing tracked yet. Add a symbol above.</div>
        ) : (
          <div className="panel tbl-scroll">
            <table>
              <thead>
                <tr>
                  <th className="wl-sort" onClick={() => toggleSort('symbol')} title="Sort by name">Symbol{sortInd('symbol')}</th>
                  <th className="r wl-sort" onClick={() => toggleSort('price')} title="Sort by price">Price{sortInd('price')}</th>
                  <th className="r">Day change</th>
                  <th className="r">Since added</th><th>Why</th><th>Sector</th><th></th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((r) => (
                  <WatchlistRow key={r.symbol} row={r} onOpen={() => setOpen(r)}
                    onRemove={() => remove(r.symbol)} onUpdate={(patch) => updateEntry(r.symbol, patch)} />
                ))}
              </tbody>
            </table>
            {sorted.length > PAGE_SIZE && (
              <div className="wl-pager">
                <button className="btn ghost" disabled={curPage <= 1} onClick={() => setPage(curPage - 1)}>← Prev</button>
                <span className="sub" style={{ margin: 0 }}>
                  Page {curPage} of {totalPages} · {sorted.length} symbols
                </span>
                <button className="btn ghost" disabled={curPage >= totalPages} onClick={() => setPage(curPage + 1)}>Next →</button>
              </div>
            )}
          </div>
        )}
    </div>
  )
}

// Tab bar of named watchlists (managers). Each tab switches the active list; the
// active tab exposes inline rename and delete. Capped at MAX_WATCHLISTS.
function WatchlistTabs({ lists, activeId, onSelect, onCreate, onRename, onDelete, err }) {
  const [editingId, setEditingId] = useState(null)
  const [name, setName] = useState('')

  if (!lists) return <div className="sub" style={{ marginBottom: 10 }}>Loading watchlists…</div>

  function startRename(l) { setEditingId(l.id); setName(l.name) }
  function commitRename() {
    const n = name.trim()
    if (editingId && n) onRename(editingId, n)
    setEditingId(null)
  }

  return (
    <div style={{ marginBottom: 12 }}>
      <div className="wl-tabs">
        {lists.map((l) => {
          const on = l.id === activeId
          if (editingId === l.id) {
            return (
              <input key={l.id} className="wl-tab-edit" autoFocus value={name}
                onChange={(e) => setName(e.target.value)}
                onBlur={commitRename}
                onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); if (e.key === 'Escape') setEditingId(null) }} />
            )
          }
          return (
            <button key={l.id} className={`wl-tab${on ? ' on' : ''}`} onClick={() => onSelect(l.id)}
              onDoubleClick={() => startRename(l)} title={on ? 'Double-click to rename' : l.name}>
              <span>{l.name}</span>
              <span className="wl-tab-count">{l.count}</span>
              {on && (
                <>
                  <span className="wl-tab-act" title="Rename"
                    onClick={(e) => { e.stopPropagation(); startRename(l) }}>✎</span>
                  {lists.length > 1 && (
                    <span className="wl-tab-act" title="Delete this watchlist"
                      onClick={(e) => { e.stopPropagation(); if (confirm(`Delete watchlist “${l.name}”? Its symbols will be removed.`)) onDelete(l.id) }}>🗑</span>
                  )}
                </>
              )}
            </button>
          )
        })}
        <button className="wl-tab wl-tab-new" onClick={onCreate}
          disabled={lists.length >= MAX_WATCHLISTS}
          title={lists.length >= MAX_WATCHLISTS ? `Limit of ${MAX_WATCHLISTS} watchlists reached` : 'New watchlist'}>
          + New
        </button>
      </div>
      {err && <div className="err" style={{ marginTop: 8 }}>⚠ {err}</div>}
    </div>
  )
}

// Email-alert controls: shows whether sending is configured, sends a one-off test
// email, and triggers the target-price / alert-date sweep on demand (otherwise it
// runs every ~15 min in the background).
function AlertsBar() {
  const s = useAsync(() => api.alertsStatus(), [])
  const [to, setTo] = useState('')
  const [msg, setMsg] = useState(null)      // { ok, text }
  const [busy, setBusy] = useState(false)

  async function sendTest() {
    if (!to.trim()) { setMsg({ ok: false, text: 'Enter an email first' }); return }
    setBusy(true); setMsg(null)
    try {
      await api.alertsTest(to.trim())
      setMsg({ ok: true, text: `Test email sent to ${to.trim()} — check inbox/spam` })
    } catch (e) { setMsg({ ok: false, text: e.message }) } finally { setBusy(false) }
  }

  async function checkNow() {
    setBusy(true); setMsg(null)
    try {
      const r = await api.alertsCheckNow()
      setMsg({ ok: true, text: r.skipped ? r.skipped : `Sweep done — ${r.sent} alert email(s) sent` })
    } catch (e) { setMsg({ ok: false, text: e.message }) } finally { setBusy(false) }
  }

  const configured = s.data?.configured
  return (
    <div className="panel" style={{ padding: 12, marginBottom: 12 }}>
      <div className="row" style={{ gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <strong style={{ fontSize: 14 }}>📧 Email alerts</strong>
        {s.loading ? <span className="sub" style={{ margin: 0 }}>checking…</span> : (
          <span className={configured ? 'up' : 'down'} style={{ fontSize: 13 }}>
            {configured ? `● Ready (from ${s.data.from})` : '● Not configured — set alert_smtp_password'}
          </span>
        )}
        <span style={{ flex: 1 }} />
        <input type="email" placeholder="test to email…" value={to} style={{ minWidth: 200 }}
          onChange={(e) => setTo(e.target.value)} />
        <button className="btn ghost" disabled={busy} onClick={sendTest}>Send test</button>
        <button className="btn ghost" disabled={busy} onClick={checkNow} title="Run the target/alert-date sweep now">
          Check alerts now
        </button>
      </div>
      {msg && (
        <div className={msg.ok ? 'up' : 'err'} style={{ marginTop: 8, fontSize: 13 }}>
          {msg.ok ? '✓ ' : '⚠ '}{msg.text}
        </div>
      )}
      <p className="sub" style={{ margin: '8px 0 0' }}>
        Alerts email the owning manager when a symbol hits its Target ₹ or its Alert date arrives.
      </p>
    </div>
  )
}

function WatchlistRow({ row: r, onOpen, onRemove, onUpdate }) {
  const [why, setWhy] = useState(r.why || '')
  // The select holds '' for "auto" (no override) or the overriding sector name.
  const sectorValue = r.sector_custom ? (r.sector || '') : ''

  function changeSector(v) {
    // '' clears the override → backend falls back to the auto-detected sector.
    if (v !== sectorValue) onUpdate({ sector: v })
  }
  // If a saved override isn't one of the standard options, keep it selectable.
  const extraSector = sectorValue && !SECTORS.includes(sectorValue) ? sectorValue : null

  return (
    <tr className="click" onClick={onOpen}>
      <td style={{ fontWeight: 600, color: 'var(--accent-ink)' }}>
        {r.symbol}
        {r.alert_hit && <span className="up" style={{ marginLeft: 6 }} title="Price reached target">●</span>}
      </td>
      <td className="r tnum">{r.price ?? '—'}</td>
      <td className="r tnum">
        {r.change_pct === null || r.change_pct === undefined ? '—' : (
          <span className={r.change_pct >= 0 ? 'up' : 'down'}>
            {r.change_pct >= 0 ? '+' : ''}{r.change_pct}% ({r.change >= 0 ? '+' : ''}{r.change})
          </span>
        )}
      </td>
      <td className="r tnum" title={r.added_price != null ? `Added @ ${inrFull(r.added_price)} on ${r.added_date || '—'}` : ''}>
        {r.diff === null || r.diff === undefined ? '—' : (
          <span className={r.diff >= 0 ? 'up' : 'down'}>{pct(r.diff_pct)}</span>
        )}
      </td>
      <td onClick={(e) => e.stopPropagation()}>
        <textarea className="journal-cell journal-cell-multiline" placeholder="Why watching…" value={why} rows={2}
          onChange={(e) => setWhy(e.target.value)}
          onBlur={() => { if (why !== (r.why || '')) onUpdate({ why }) }} />
      </td>
      <td onClick={(e) => e.stopPropagation()}>
        <select className="journal-cell" style={{ minWidth: 150 }} value={sectorValue}
          title={r.sector_custom ? 'Custom sector — pick “Auto” to revert' : 'Override sector'}
          onChange={(e) => changeSector(e.target.value)}>
          <option value="">{`Auto · ${r.auto_sector || 'Unclassified'}`}</option>
          {SECTORS.map((s) => <option key={s} value={s}>{s}</option>)}
          {extraSector && <option value={extraSector}>{extraSector}</option>}
        </select>
      </td>
      <td className="r">
        <button className="btn ghost" style={{ padding: '4px 10px' }}
          onClick={(e) => { e.stopPropagation(); onRemove() }}>Remove</button>
      </td>
    </tr>
  )
}
