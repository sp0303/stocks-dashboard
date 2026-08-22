import React, { useState, useRef, useEffect } from 'react'
import {
  PieChart, Pie, Cell, Sector, ResponsiveContainer, Tooltip, LineChart, Line, XAxis, YAxis, CartesianGrid,
} from 'recharts'
import { api, inr, inrFull, pct, pctPlain } from '../api.js'
import { Stat, PnL, Loading, ErrorBox, useAsync, PALETTE } from './common.jsx'
import StockAnalysis from './StockAnalysis.jsx'
import Watchlist from './Watchlist.jsx'

export default function ClientDashboard({ client }) {
  const [tab, setTab] = useState('overview')
  const [reload, setReload] = useState(0)
  const [symbol, setSymbol] = useState(null) // drilled into a single stock
  const tabs = [
    { key: 'overview', icon: '▤' },
    { key: 'holdings', icon: '▦' },
    { key: 'allocation', icon: '◔' },
    { key: 'performance', icon: '📈' },
    { key: 'trades', icon: '⇅' },
    { key: 'watchlist', icon: '★' },
  ]

  if (symbol) {
    return <StockAnalysis client={client} symbol={symbol} onBack={() => setSymbol(null)} />
  }

  return (
    <div>
      <h1>{client.name}</h1>
      <p className="sub mono">{client.client_code || 'no broker code'} · onboarded {String(client.onboarded_at || '').slice(0, 10)}</p>

      <UploadBar client={client} onDone={() => setReload((n) => n + 1)} />

      <div className="dash-shell">
        <nav className="dash-nav">
          {tabs.map((t) => (
            <button key={t.key} className={tab === t.key ? 'on' : ''} onClick={() => setTab(t.key)}>
              <span className="navico">{t.icon}</span>{t.key[0].toUpperCase() + t.key.slice(1)}
            </button>
          ))}
        </nav>

        <div className="dash-main">
          {tab === 'overview' && <Overview client={client} reload={reload} />}
          {tab === 'holdings' && <Holdings client={client} reload={reload} onOpenStock={setSymbol} />}
          {tab === 'allocation' && <Allocation client={client} reload={reload} />}
          {tab === 'performance' && <Performance client={client} reload={reload} />}
          {tab === 'trades' && <Trades client={client} reload={reload} onOpenStock={setSymbol} />}
          {tab === 'watchlist' && <Watchlist scope="clients" id={client.id} title="Client watchlist" />}
        </div>
      </div>
    </div>
  )
}

function UploadBar({ client, onDone }) {
  const inputRef = useRef()
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)

  async function upload(file) {
    if (!file) return
    setBusy(true); setMsg(null)
    try {
      const r = await api.uploadTradebook(client.id, file)
      const s = r.summary
      setMsg({ ok: true, text: `Imported ${s.imported} trades (${s.duplicates} duplicates skipped, ${s.errors} errors).` })
      onDone()
    } catch (e) {
      setMsg({ ok: false, text: e.message })
    } finally {
      setBusy(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <div className="panel" style={{ padding: 14, marginTop: 8 }}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div>
          <strong>Upload tradebook</strong>
          <div className="sub" style={{ margin: 0 }}>Zerodha equity export (.xlsx). Re-uploads dedupe automatically.</div>
        </div>
        <div className="row">
          <input ref={inputRef} type="file" accept=".xlsx,.xls" onChange={(e) => upload(e.target.files[0])} disabled={busy} />
        </div>
      </div>
      {busy && <div className="loading" style={{ padding: '8px 0 0' }}>Parsing & pricing…</div>}
      {msg && <div style={{ marginTop: 10 }} className={msg.ok ? '' : 'err'}>{msg.ok ? '✓ ' : ''}{msg.text}</div>}
    </div>
  )
}

// Enlarges the hovered pie slice (recharts' controlled active-shape pattern).
function renderActiveSlice(props) {
  const { cx, cy, innerRadius, outerRadius, startAngle, endAngle, fill } = props
  return (
    <Sector
      cx={cx} cy={cy} innerRadius={innerRadius} outerRadius={outerRadius + 8}
      startAngle={startAngle} endAngle={endAngle} fill={fill}
    />
  )
}

// "Current" = weighted by today's market value (live prices, mark-to-market split).
// "Invested" = weighted by original cost/invested value (how capital was actually
// deployed — unaffected by subsequent price moves, useful for spotting drift).
function BasisToggle({ basis, setBasis }) {
  return (
    <div className="tabs" style={{ borderBottom: 'none', margin: '8px 0' }}>
      {[['current', 'Current'], ['invested', 'Invested']].map(([k, label]) => (
        <button key={k} className={basis === k ? 'on' : ''} onClick={() => setBasis(k)}>{label}</button>
      ))}
    </div>
  )
}

// Pie + legend table, hover-synced both ways: hovering a table row (or a slice)
// enlarges that slice and dims the rest so it's unambiguous which is which.
function AllocationChart({ data, height = 300, outerRadius = 110, innerRadius = 55, labelKey = 'key' }) {
  const [hover, setHover] = useState(null)
  return (
    <div className="grid2">
      <div className="panel" style={{ padding: 12, minHeight: height }}>
        <ResponsiveContainer width="100%" height={height}>
          <PieChart>
            <Pie
              data={data} dataKey="value" nameKey="key" cx="50%" cy="50%"
              outerRadius={outerRadius} innerRadius={innerRadius}
              label={({ pct: p }) => `${p}%`}
              labelLine={{ stroke: 'var(--muted)' }}
              activeIndex={hover === null ? undefined : hover}
              activeShape={renderActiveSlice}
              onMouseEnter={(_, i) => setHover(i)}
              onMouseLeave={() => setHover(null)}
            >
              {data.map((_, i) => (
                <Cell
                  key={i}
                  fill={PALETTE[i % PALETTE.length]}
                  fillOpacity={hover === null || hover === i ? 1 : 0.35}
                />
              ))}
            </Pie>
            <Tooltip formatter={(v, n, item) => [`${inrFull(v)} (${item.payload.pct}%)`, n]} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="panel tbl-scroll">
        <table>
          <thead><tr><th>{labelKey}</th><th className="r">Value</th><th className="r">Weight</th></tr></thead>
          <tbody>
            {data.map((r, i) => (
              <tr key={r.key} className={hover === i ? 'hl' : ''} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                <td><span className="dot" style={{ background: PALETTE[i % PALETTE.length] }} />{r.key}</td>
                <td className="r tnum">{inrFull(r.value)}</td>
                <td className="r tnum">{r.pct}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Overview({ client, reload }) {
  const [basis, setBasis] = useState('current')
  const p = useAsync(() => api.portfolio(client.id), [client.id, reload])
  const c = useAsync(() => api.concentration(client.id), [client.id, reload])
  const alloc = useAsync(() => api.allocation(client.id, 'sector', basis), [client.id, reload, basis])
  if (p.loading) return <Loading what="portfolio" />
  if (p.error) return <ErrorBox error={p.error} />
  const d = p.data
  if (!d.total_trades) return <div className="empty">No trades yet. Upload a tradebook above to see the portfolio.</div>
  return (
    <div>
      <div className="cards">
        <Stat label="Market Value" value={inr(d.market_value)} sub={inrFull(d.market_value)} />
        <Stat label="Invested" value={inr(d.invested_value)} sub={inrFull(d.invested_value)} />
        <Stat label="Total P&L" value={inr(d.total_pnl)} tone={d.total_pnl >= 0 ? 'up' : 'down'} sub={pct(d.return_pct) + ' return'} />
        <Stat label="Realized P&L" value={inr(d.realized_pnl)} tone={d.realized_pnl >= 0 ? 'up' : 'down'} />
        <Stat label="Unrealized P&L" value={inr(d.unrealized_pnl)} tone={d.unrealized_pnl >= 0 ? 'up' : 'down'} />
        <Stat label="Open positions" value={d.open_positions} sub={`${d.total_trades} trades`} />
      </div>
      {!c.loading && !c.error && c.data.largest_stock && (
        <>
          <h2>Concentration</h2>
          <div className="cards">
            <Stat label="Top 5 holdings" value={pctPlain(c.data.top5_pct)} sub="of portfolio" />
            <Stat label="Largest stock" value={`${c.data.largest_stock.symbol}`} sub={pctPlain(c.data.largest_stock.pct)} />
            <Stat label="Largest sector" value={c.data.largest_sector.key} sub={pctPlain(c.data.largest_sector.pct)} />
          </div>
        </>
      )}
      {!alloc.loading && !alloc.error && alloc.data.length > 0 && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
            <h2 style={{ margin: 0 }}>Sector allocation</h2>
            <BasisToggle basis={basis} setBasis={setBasis} />
          </div>
          <AllocationChart data={alloc.data} height={260} outerRadius={95} innerRadius={45} labelKey="Sector" />
        </>
      )}
    </div>
  )
}

function Holdings({ client, reload, onOpenStock }) {
  const h = useAsync(() => api.holdings(client.id), [client.id, reload])
  if (h.loading) return <Loading what="holdings" />
  if (h.error) return <ErrorBox error={h.error} />
  const rows = h.data.holdings
  if (!rows.length) return <div className="empty">No open holdings.</div>
  return (
    <div>
      <p className="sub">Click any stock to see its full journey and transaction timeline.</p>
      <div className="panel tbl-scroll">
      <table>
        <thead>
          <tr>
            <th>Stock</th><th className="r">Qty</th><th className="r">Avg cost</th><th className="r">LTP</th>
            <th className="r">Invested</th><th className="r">Value</th><th className="r">Unrealized</th>
            <th className="r">P&L %</th><th className="r">Weight</th><th>Sector</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.symbol} className="click" onClick={() => onOpenStock(r.symbol)}>
              <td style={{ fontWeight: 600, color: 'var(--accent-ink)' }}>{r.symbol}{r.stale && <span className="stale">stale</span>}</td>
              <td className="r tnum">{r.quantity}</td>
              <td className="r tnum">{r.avg_cost}</td>
              <td className="r tnum">{r.ltp ?? '—'}</td>
              <td className="r tnum">{inrFull(r.invested_value)}</td>
              <td className="r tnum">{inrFull(r.market_value)}</td>
              <td className="r tnum"><span className={r.unrealized_pnl >= 0 ? 'up' : 'down'}>{inrFull(r.unrealized_pnl)}</span></td>
              <td className="r tnum"><PnL value={r.unrealized_pct} /></td>
              <td className="r tnum">{r.portfolio_pct ? r.portfolio_pct + '%' : '—'}</td>
              <td>{r.sector}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  )
}

function Allocation({ client, reload }) {
  const [by, setBy] = useState('sector')
  const [basis, setBasis] = useState('current')
  const a = useAsync(() => api.allocation(client.id, by, basis), [client.id, by, basis, reload])
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
        <div className="tabs" style={{ borderBottom: 'none', margin: '8px 0' }}>
          {['sector', 'cap', 'asset', 'stock'].map((k) => (
            <button key={k} className={by === k ? 'on' : ''} onClick={() => setBy(k)}>{k[0].toUpperCase() + k.slice(1)}</button>
          ))}
        </div>
        <BasisToggle basis={basis} setBasis={setBasis} />
      </div>
      {a.loading ? <Loading what="allocation" /> : a.error ? <ErrorBox error={a.error} /> : !a.data.length ? (
        <div className="empty">Nothing to allocate yet.</div>
      ) : (
        <AllocationChart data={a.data} height={300} outerRadius={110} innerRadius={55} labelKey={by[0].toUpperCase() + by.slice(1)} />
      )}
    </div>
  )
}

function Performance({ client, reload }) {
  const p = useAsync(() => api.performance(client.id), [client.id, reload])
  if (p.loading) return <Loading what="performance" />
  if (p.error) return <ErrorBox error={p.error} />
  if (!p.data.length) return <div className="empty">No history yet.</div>
  return (
    <div>
      <p className="sub">Capital deployed and realized P&L over time (cost-basis view — no price backfill needed).</p>
      <div className="panel" style={{ padding: 16 }}>
        <ResponsiveContainer width="100%" height={330}>
          <LineChart data={p.data} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--muted)' }} minTickGap={40} />
            <YAxis tick={{ fontSize: 11, fill: 'var(--muted)' }} tickFormatter={(v) => inr(v)} width={62} />
            <Tooltip formatter={(v) => inrFull(v)} />
            <Line type="monotone" dataKey="invested_value" name="Invested" stroke="#3a86c8" dot={false} strokeWidth={2} />
            <Line type="monotone" dataKey="realized_pnl" name="Realized P&L" stroke="#0f7a5a" dot={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

// Zerodha-Console-style tag colors — reuse the allocation palette so the whole app
// reads as one system.
const TAG_COLORS = PALETTE

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
// "2026-08-14" -> "14 Aug" — full date still on hover via title. Dense enough for a
// fixed-width trades column without needing horizontal scroll to read it.
function shortDate(iso) {
  if (!iso) return '—'
  const [, m, d] = iso.split('-')
  return `${parseInt(d, 10)} ${MONTHS[parseInt(m, 10) - 1] || m}`
}

function TagChip({ tag, onRemove }) {
  return (
    <span className="tag-chip" style={{ background: `${tag.color}26`, color: tag.color, borderColor: `${tag.color}55` }}>
      {tag.name}
      {onRemove && <button type="button" className="tag-chip-x" onClick={(e) => { e.stopPropagation(); onRemove() }}>×</button>}
    </span>
  )
}

// Inline tag editor for one trade — replaces free-text notes with reusable, named,
// colored tags (matches Zerodha Console's tagging journal). Rendered as a full-width
// row directly under the trade so it never needs a floating popover that could get
// clipped by the table's scroll container.
function TagEditorRow({ trade, allTags, appliedIds, onToggle, onCreateAndApply, colSpan }) {
  const [name, setName] = useState('')
  const [color, setColor] = useState(TAG_COLORS[0])

  const submit = () => {
    const n = name.trim()
    if (!n) return
    onCreateAndApply(n, color)
    setName('')
  }

  return (
    <tr className="tag-editor-row">
      <td colSpan={colSpan}>
        <div className="tag-editor">
          <div className="tag-editor-existing">
            {allTags.length === 0 ? (
              <span className="sub" style={{ margin: 0 }}>No tags yet — create the first one below.</span>
            ) : (
              allTags.map((t) => {
                const on = appliedIds.includes(t.id)
                return (
                  <button
                    key={t.id}
                    type="button"
                    className={`tag-toggle ${on ? 'on' : ''}`}
                    style={on ? { background: `${t.color}26`, color: t.color, borderColor: t.color } : {}}
                    onClick={() => onToggle(t.id)}
                    title={t.description || t.name}
                  >
                    <span className="dot" style={{ background: t.color }} />{t.name}
                  </button>
                )
              })
            )}
          </div>
          <div className="tag-editor-new">
            <input
              placeholder="New tag name, e.g. Earnings play"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && submit()}
            />
            <div className="tag-color-picker">
              {TAG_COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  className={`tag-swatch ${color === c ? 'on' : ''}`}
                  style={{ background: c }}
                  onClick={() => setColor(c)}
                />
              ))}
            </div>
            <button type="button" className="btn" onClick={submit}>+ Add & apply</button>
          </div>
        </div>
      </td>
    </tr>
  )
}

// Compact single-line "why" note — the one-off rationale for this specific trade,
// alongside the reusable tags. Same debounce-on-blur discipline as before: no API
// call per keystroke across a 500-row table.
function NoteCell({ value, onSave }) {
  const [val, setVal] = useState(value || '')
  const saved = useRef(value || '')
  useEffect(() => { setVal(value || ''); saved.current = value || '' }, [value])
  return (
    <input
      className="journal-cell"
      placeholder="Why this trade…"
      value={val}
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => setVal(e.target.value)}
      onBlur={() => {
        if (val !== saved.current) {
          saved.current = val
          onSave(val)
        }
      }}
    />
  )
}

function Trades({ client, reload, onOpenStock }) {
  const [q, setQ] = useState('')
  const [tagFilter, setTagFilter] = useState('')
  const [expanded, setExpanded] = useState(null) // fingerprint of the row being tagged
  const [override, setOverride] = useState({}) // fingerprint -> tag_ids, optimistic local wins
  const t = useAsync(() => api.trades(client.id, { tag: tagFilter || undefined }), [client.id, reload, tagFilter])
  const tagsQ = useAsync(() => api.tags(client.id), [client.id, reload])

  if (t.loading || tagsQ.loading) return <Loading what="trades" />
  if (t.error) return <ErrorBox error={t.error} />
  const allTags = tagsQ.data || []
  const tagsById = Object.fromEntries(allTags.map((tg) => [tg.id, tg]))
  const rows = t.data.data.filter((r) => !q || r.symbol.includes(q.toUpperCase()))

  const appliedFor = (r) => override[r.fingerprint] ?? r.tag_ids ?? []

  const toggleTag = (r, tagId) => {
    const current = appliedFor(r)
    const next = current.includes(tagId) ? current.filter((id) => id !== tagId) : [...current, tagId]
    setOverride((o) => ({ ...o, [r.fingerprint]: next }))
    api.setTradeTags(client.id, r.fingerprint, next).catch(() => {})
  }

  const createAndApply = async (r, name, color) => {
    try {
      const tag = await api.createTag(client.id, { name, color })
      tagsQ.data.push(tag) // reflect immediately without a full refetch
      toggleTag(r, tag.id)
    } catch { /* ignore */ }
  }

  const saveNote = (fingerprint, note) => {
    api.setTradeNote(client.id, fingerprint, note).catch(() => {})
  }

  return (
    <div>
      <div className="row" style={{ marginBottom: 10, flexWrap: 'wrap' }}>
        <input placeholder="Filter by symbol…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={tagFilter} onChange={(e) => setTagFilter(e.target.value)}>
          <option value="">All tags</option>
          {allTags.map((tg) => <option key={tg.id} value={tg.id}>{tg.name}</option>)}
        </select>
        <span className="sub" style={{ margin: 0 }}>{rows.length} of {t.data.meta.total} trades</span>
      </div>
      <p className="sub">Why you took a trade, plus tags to categorize it — click a trade's tags to add or create one.</p>
      <div className="panel tbl-scroll" style={{ maxHeight: 560, overflowY: 'auto' }}>
        <table className="trades-table">
          <colgroup>
            <col style={{ width: '7%' }} /><col style={{ width: '12%' }} /><col style={{ width: '4%' }} />
            <col style={{ width: '6%' }} /><col style={{ width: '8%' }} /><col style={{ width: '11%' }} />
            <col style={{ width: '26%' }} /><col style={{ width: '26%' }} />
          </colgroup>
          <thead>
            <tr>
              <th>Date</th><th>Symbol</th><th>Type</th><th className="r">Qty</th><th className="r">Price</th><th className="r">Value</th><th>Why</th><th>Tags</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 500).map((r) => {
              const applied = appliedFor(r).map((id) => tagsById[id]).filter(Boolean)
              const isOpen = expanded === r.fingerprint
              return (
                <React.Fragment key={r.id || r.fingerprint}>
                  <tr className="click" onClick={() => onOpenStock(r.symbol)}>
                    <td className="mono" title={r.trade_date}>{shortDate(r.trade_date)}</td>
                    <td style={{ fontWeight: 600, color: 'var(--accent-ink)' }}>
                      {r.symbol}{r.exchange && r.exchange !== 'NSE' && <span className="exch-badge">{r.exchange}</span>}
                    </td>
                    <td><span className={`badge ${r.trade_type}`} title={r.trade_type}>{r.trade_type === 'buy' ? 'B' : 'S'}</span></td>
                    <td className="r tnum">{r.quantity}</td>
                    <td className="r tnum">{r.price}</td>
                    <td className="r tnum">{inrFull(r.trade_value)}</td>
                    <td>
                      <NoteCell value={r.note} onSave={(v) => saveNote(r.fingerprint, v)} />
                    </td>
                    <td>
                      <div className="tag-cell" onClick={(e) => { e.stopPropagation(); setExpanded(isOpen ? null : r.fingerprint) }}>
                        {applied.map((tg) => <TagChip key={tg.id} tag={tg} />)}
                        <button type="button" className="tag-add">{applied.length ? '+' : '+ Tag'}</button>
                      </div>
                    </td>
                  </tr>
                  {isOpen && (
                    <TagEditorRow
                      trade={r}
                      allTags={allTags}
                      appliedIds={appliedFor(r)}
                      onToggle={(tagId) => toggleTag(r, tagId)}
                      onCreateAndApply={(name, color) => createAndApply(r, name, color)}
                      colSpan={8}
                    />
                  )}
                </React.Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
