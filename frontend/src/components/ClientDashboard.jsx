import React, { useState, useRef, useEffect } from 'react'
import {
  PieChart, Pie, Cell, Sector, ResponsiveContainer, Tooltip, LineChart, Line, XAxis, YAxis, CartesianGrid,
} from 'recharts'
import { api, inr, inrFull, pct, pctPlain } from '../api.js'
import { Stat, PnL, Loading, ErrorBox, useAsync, PALETTE } from './common.jsx'
import StockAnalysis from './StockAnalysis.jsx'
import Watchlist from './Watchlist.jsx'

const TABS = [
  { key: 'overview', icon: '▤', title: 'Overview' },
  { key: 'holdings', icon: '▦', title: 'Holdings' },
  { key: 'allocation', icon: '◔', title: 'Allocation' },
  { key: 'performance', icon: '📈', title: 'Performance' },
  { key: 'dividends', icon: '💰', title: 'Dividends' },
  { key: 'trades', icon: '⇅', title: 'Trades' },
  { key: 'watchlist', icon: '★', title: 'Watchlist' },
]

// One continuously-scrolling page: every section is always mounted, the nav
// highlights whichever section is under the sticky header as you scroll, and
// clicking a nav item still jumps straight there.
function Section({ sectionKey, title, sectionRef, children }) {
  return (
    <section ref={sectionRef} id={`section-${sectionKey}`} className="dash-section">
      {title && <h2 className="section-title">{title}</h2>}
      {children}
    </section>
  )
}

export default function ClientDashboard({ client }) {
  const [tab, setTab] = useState('overview')
  const [reload, setReload] = useState(0)
  const [symbol, setSymbol] = useState(null) // drilled into a single stock
  const sectionRefs = useRef({})

  if (symbol) {
    return <StockAnalysis client={client} symbol={symbol} onBack={() => setSymbol(null)} />
  }

  function goToTab(key) {
    setTab(key)
    sectionRefs.current[key]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div>
      <h1>{client.name}</h1>
      <p className="sub mono">{client.client_code || 'no broker code'} · onboarded {String(client.onboarded_at || '').slice(0, 10)}</p>

      <AISummaryCard client={client} reload={reload} />

      <UploadBar client={client} onDone={() => setReload((n) => n + 1)} />

      <div className="dash-shell">
        <nav className="dash-nav">
          {TABS.map((t) => (
            <button key={t.key} className={tab === t.key ? 'on' : ''} onClick={() => goToTab(t.key)}>
              <span className="navico">{t.icon}</span>{t.title}
            </button>
          ))}
        </nav>

        <ScrollSpyMain sectionRefs={sectionRefs} setTab={setTab}>
          <Section sectionKey="overview" title="Overview" sectionRef={(el) => (sectionRefs.current.overview = el)}>
            <OverviewSection client={client} reload={reload} />
          </Section>
          <Section sectionKey="holdings" title="Holdings" sectionRef={(el) => (sectionRefs.current.holdings = el)}>
            <HoldingsSection client={client} reload={reload} onOpenStock={setSymbol} />
          </Section>
          <Section sectionKey="allocation" title="Allocation" sectionRef={(el) => (sectionRefs.current.allocation = el)}>
            <AllocationSection client={client} reload={reload} />
          </Section>
          <Section sectionKey="performance" title="Performance" sectionRef={(el) => (sectionRefs.current.performance = el)}>
            <PerformanceSection client={client} reload={reload} />
          </Section>
          <Section sectionKey="dividends" title="Dividends" sectionRef={(el) => (sectionRefs.current.dividends = el)}>
            <DividendsSection client={client} />
          </Section>
          <Section sectionKey="trades" title="Trades" sectionRef={(el) => (sectionRefs.current.trades = el)}>
            <TradesSection client={client} reload={reload} onOpenStock={setSymbol} />
          </Section>
          <Section sectionKey="watchlist" sectionRef={(el) => (sectionRefs.current.watchlist = el)}>
            <Watchlist scope="clients" id={client.id} title="Client watchlist" />
          </Section>
        </ScrollSpyMain>
      </div>
    </div>
  )
}

// Tracks which mounted section sits just under the sticky header and keeps the
// nav's active tab in sync as the user scrolls; independent of click-driven jumps.
// Section components are React.memo'd so this doesn't force them to re-render on
// every scroll tick — only the nav highlight (owned by the parent) updates.
function ScrollSpyMain({ sectionRefs, setTab, children }) {
  useEffect(() => {
    const line = 130 // px from viewport top — below the sticky topbar
    let queued = false
    const pick = () => {
      queued = false
      const entries = Object.entries(sectionRefs.current).filter(([, el]) => el)
      let best = entries[0]?.[0]
      let bestTop = -Infinity
      for (const [key, el] of entries) {
        const top = el.getBoundingClientRect().top
        if (top <= line && top > bestTop) { bestTop = top; best = key }
      }
      if (best) setTab((prev) => (prev === best ? prev : best))
    }
    // time-based throttle rather than requestAnimationFrame: rAF is heavily capped
    // (often ~1fps) in backgrounded/inactive tabs, so a plain timer keeps this
    // responsive even when the tab isn't the active one.
    const onScroll = () => {
      if (queued) return
      queued = true
      setTimeout(pick, 60)
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    pick()
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return <div className="dash-main">{children}</div>
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
        <div className="row upload-file-row">
          <input ref={inputRef} type="file" accept=".xlsx,.xls" onChange={(e) => upload(e.target.files[0])} disabled={busy} />
        </div>
      </div>
      {busy && <div className="loading" style={{ padding: '8px 0 0' }}>Parsing & pricing…</div>}
      {msg && <div style={{ marginTop: 10 }} className={msg.ok ? '' : 'err'}>{msg.ok ? '✓ ' : ''}{msg.text}</div>}
    </div>
  )
}

// Splits an LLM narrative into bullet points regardless of whether the model used
// "* " markers on one line or actual newlines — both show up across runs/models.
function splitNarrative(text) {
  return text
    .replace(/(^|\s)\*\s+/g, '\n')
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean)
}

// Bolds a leading "Label:" so scanned bullets read like a stat, not a sentence.
function NarrativeLine({ text }) {
  const m = text.match(/^([A-Za-z][A-Za-z\s]{0,28}:)\s*(.*)$/)
  if (!m) return <li>{text}</li>
  return <li><b>{m[1]}</b> {m[2]}</li>
}

// Top-of-page AI insight card — narrates the holding-summary metrics (never a
// source of numbers itself; see backend/app/services/llm.py). Fetched independently
// of everything else on the page since it's the one call that hits a live LLM.
function AISummaryCard({ client, reload }) {
  const n = useAsync(() => api.holdingSummaryNarrative(client.id), [client.id, reload])
  if (n.error) return null // quietly omit — the rest of the dashboard doesn't depend on this
  const lines = n.data?.narrative ? splitNarrative(n.data.narrative) : []
  if (!n.loading && !lines.length) return null
  return (
    <div className="ai-summary">
      <div className="ai-summary-head">
        <span className="ai-summary-badge">AI summary</span>
        <h2>Holding highlights</h2>
      </div>
      {n.loading ? (
        <Loading what="summary" />
      ) : (
        <ul>
          {lines.map((line, i) => <NarrativeLine key={i} text={line} />)}
        </ul>
      )}
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
      <Playbook client={client} reload={reload} />
    </div>
  )
}

const PLAYBOOK_COLUMNS = [
  { key: 'symbol', label: 'Stock' },
  { key: 'quantity', label: 'Qty', r: true },
  { key: 'buy_price', label: 'Buy Price', r: true },
  { key: 'buy_date', label: 'Buy Date' },
  { key: 'sell_price', label: 'Sell Price', r: true },
  { key: 'sell_date', label: 'Sell Date' },
  { key: 'days', label: 'Days', r: true },
  { key: 'pnl', label: 'PNL', r: true },
  { key: 'pnl_pct', label: 'PNL %', r: true },
  { key: 'reason', label: 'Reason for buying' },
]

const PLAYBOOK_PAGE_SIZE = 10

// Round-trip (bought-then-sold) trade history, FIFO-matched on the backend.
// Plain 10-row pages with Prev/Next, same pattern as the Trades table below.
function Playbook({ client, reload }) {
  const [sort, setSort] = useState('sell_date')
  const [order, setOrder] = useState('desc')
  const [page, setPage] = useState(1)
  const pb = useAsync(
    () => api.playbook(client.id, { sort, order, page, pageSize: PLAYBOOK_PAGE_SIZE }),
    [client.id, reload, sort, order, page]
  )
  const rows = pb.data?.data || []
  const meta = pb.data?.meta || { total: 0, pages: 1 }

  function toggleSort(key) {
    if (sort === key) {
      setOrder((o) => (o === 'desc' ? 'asc' : 'desc'))
    } else {
      setSort(key)
      setOrder('desc')
    }
    setPage(1)
  }

  return (
    <div style={{ marginTop: 24 }}>
      <h2>Playbook</h2>
      <p className="sub">Closed round trips — every buy matched FIFO against its sell. Click a column to sort.</p>
      {pb.loading && <Loading what="playbook" />}
      {pb.error && <ErrorBox error={pb.error} />}
      {!pb.loading && !pb.error && !rows.length && (
        <div className="empty">No closed trades yet.</div>
      )}
      {!pb.loading && !pb.error && rows.length > 0 && (
        <>
          <div className="panel tbl-scroll">
            <table>
              <thead>
                <tr>
                  {PLAYBOOK_COLUMNS.map((c) => (
                    <th
                      key={c.key}
                      className={c.r ? 'r click' : 'click'}
                      onClick={() => toggleSort(c.key)}
                    >
                      {c.label}{sort === c.key ? (order === 'desc' ? ' ▾' : ' ▴') : ''}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 600, color: 'var(--accent-ink)' }}>{r.symbol}</td>
                    <td className="r tnum">{r.quantity}</td>
                    <td className="r tnum">{r.buy_price}</td>
                    <td>{r.buy_date}</td>
                    <td className="r tnum">{r.sell_price}</td>
                    <td>{r.sell_date}</td>
                    <td className="r tnum">{r.days ?? '—'}</td>
                    <td className="r tnum"><span className={r.pnl >= 0 ? 'up' : 'down'}>{inrFull(r.pnl)}</span></td>
                    <td className="r tnum"><PnL value={r.pnl_pct} /></td>
                    <td>{r.reason || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {meta.pages > 1 && (
            <div className="row" style={{ justifyContent: 'center', marginTop: 12, gap: 8 }}>
              <button className="btn ghost" disabled={page === 1} onClick={() => setPage((p) => p - 1)}>← Prev</button>
              <span className="sub" style={{ margin: 0 }}>Page {page} of {meta.pages} · {meta.total} closed trades</span>
              <button className="btn ghost" disabled={page >= meta.pages} onClick={() => setPage((p) => p + 1)}>Next →</button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

const HOLDINGS_COLUMNS = [
  { key: 'symbol', label: 'Stock' },
  { key: 'quantity', label: 'Qty', r: true },
  { key: 'avg_cost', label: 'Avg cost', r: true },
  { key: 'ltp', label: 'LTP', r: true },
  { key: 'invested_value', label: 'Invested', r: true },
  { key: 'market_value', label: 'Value', r: true },
  { key: 'unrealized_pnl', label: 'Unrealized', r: true },
  { key: 'unrealized_pct', label: 'P&L %', r: true },
  { key: 'portfolio_pct', label: 'Weight', r: true },
  { key: 'sector', label: 'Sector' },
  { key: 'entry_date', label: 'Entry date' },
  { key: 'holding_days', label: 'Days held', r: true },
]

function Holdings({ client, reload, onOpenStock }) {
  const [page, setPage] = useState(0)
  const [sort, setSort] = useState({ key: 'market_value', dir: 'desc' })
  const h = useAsync(() => api.holdings(client.id), [client.id, reload])
  if (h.loading) return <Loading what="holdings" />
  if (h.error) return <ErrorBox error={h.error} />
  const rows = h.data.holdings
  if (!rows.length) return <div className="empty">No open holdings.</div>

  const toggleSort = (key) => {
    setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }))
    setPage(0)
  }
  const sorted = [...rows].sort((a, b) => {
    const av = a[sort.key], bv = b[sort.key]
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    if (typeof av === 'string') return sort.dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av)
    return sort.dir === 'asc' ? av - bv : bv - av
  })

  const pageSize = 10
  const totalPages = Math.ceil(sorted.length / pageSize)
  const paged = sorted.slice(page * pageSize, (page + 1) * pageSize)
  return (
    <div>
      <p className="sub">Click any stock to see its full journey and transaction timeline. Click a column header to sort.</p>
      <div className="panel tbl-scroll">
      <table>
        <thead>
          <tr>
            {HOLDINGS_COLUMNS.map((c) => (
              <th key={c.key} className={c.r ? 'r' : ''} style={{ cursor: 'pointer', userSelect: 'none' }}
                onClick={() => toggleSort(c.key)}>
                {c.label}{sort.key === c.key ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {paged.map((r) => (
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
              <td className="mono" title={r.entry_date || ''}>{r.entry_date ? shortDate(r.entry_date) : '—'}</td>
              <td className="r tnum">{r.holding_days ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      {totalPages > 1 && (
        <div className="row" style={{ justifyContent: 'center', marginTop: 12, gap: 8 }}>
          <button className="btn ghost" disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}>← Prev</button>
          <span className="sub" style={{ margin: 0 }}>Page {page + 1} of {totalPages}</span>
          <button className="btn ghost" disabled={page >= totalPages - 1}
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}>Next →</button>
        </div>
      )}
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
  const x = useAsync(() => api.xirr(client.id), [client.id, reload])
  if (p.loading) return <Loading what="performance" />
  if (p.error) return <ErrorBox error={p.error} />
  if (!p.data.length) return <div className="empty">No history yet.</div>
  const hasBenchmark = p.data.some((row) => row.benchmark_value != null)
  return (
    <div>
      <p className="sub">Capital deployed and realized P&L over time (cost-basis view — no price backfill needed).</p>
      {!x.loading && !x.error && (
        <div className="cards" style={{ marginBottom: 16 }}>
          <Stat
            label="XIRR"
            value={pct(x.data?.xirr != null ? x.data.xirr * 100 : null)}
            sub={x.data?.xirr != null ? 'money-weighted, incl. dividends' : 'not computable — very short, high-return round trips push the required rate off the chart'}
          />
          <Stat label="CAGR" value={pct(x.data?.cagr != null ? x.data.cagr * 100 : null)} sub="invested → market value" />
        </div>
      )}
      <div className="panel" style={{ padding: 16 }}>
        <ResponsiveContainer width="100%" height={330}>
          <LineChart data={p.data} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--muted)' }} minTickGap={40} />
            <YAxis tick={{ fontSize: 11, fill: 'var(--muted)' }} tickFormatter={(v) => inr(v)} width={62} />
            <Tooltip formatter={(v) => inrFull(v)} />
            <Line type="monotone" dataKey="invested_value" name="Invested" stroke="#3a86c8" dot={false} strokeWidth={2} />
            <Line type="monotone" dataKey="realized_pnl" name="Realized P&L" stroke="#0f7a5a" dot={false} strokeWidth={2} />
            {hasBenchmark && (
              <Line type="monotone" dataKey="benchmark_value" name="Nifty 50 (same cashflows)" stroke="#c8763a" dot={false} strokeWidth={2} strokeDasharray="4 3" />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <HoldingSummary client={client} reload={reload} />
    </div>
  )
}

const HOLDING_SUMMARY_COLUMNS = [
  { key: 'symbol', label: 'Symbol' },
  { key: 'status', label: 'Status' },
  { key: 'days_held', label: 'Days held', r: true },
  { key: 'return_pct', label: 'Return %', r: true },
  { key: 'pnl', label: 'P&L', r: true },
]

function HoldingSummary({ client, reload }) {
  const [page, setPage] = useState(0)
  const [sort, setSort] = useState({ key: 'return_pct', dir: 'desc' })
  const s = useAsync(() => api.holdingSummary(client.id), [client.id, reload])
  if (s.loading) return null
  if (s.error) return <ErrorBox error={s.error} />
  const rows = s.data.rows
  if (!rows.length) return null

  const toggleSort = (key) => {
    setSort((cur) => (cur.key === key ? { key, dir: cur.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }))
    setPage(0)
  }
  const sorted = [...rows].sort((a, b) => {
    const av = a[sort.key], bv = b[sort.key]
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    if (typeof av === 'string') return sort.dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av)
    return sort.dir === 'asc' ? av - bv : bv - av
  })

  const pageSize = 10
  const totalPages = Math.ceil(sorted.length / pageSize)
  const paged = sorted.slice(page * pageSize, (page + 1) * pageSize)
  return (
    <div className="panel tbl-scroll" style={{ padding: 16, marginTop: 16 }}>
      <h2>Holding summary</h2>
      <p className="sub">How long each position was (or is) held, and what it returned — open and closed positions, best return first. Click a column header to sort.</p>
      <table>
        <thead>
          <tr>
            {HOLDING_SUMMARY_COLUMNS.map((c) => (
              <th key={c.key} className={c.r ? 'r' : ''} style={{ cursor: 'pointer', userSelect: 'none' }}
                onClick={() => toggleSort(c.key)}>
                {c.label}{sort.key === c.key ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {paged.map((r, i) => (
            <tr key={`${r.symbol}-${r.status}-${page * pageSize + i}`}>
              <td className="mono">{r.symbol}</td>
              <td className="sub">{r.status}</td>
              <td className="tnum">{r.days_held ?? '—'}</td>
              <td className="tnum">{pct(r.return_pct)}</td>
              <td className="tnum"><span className={r.pnl >= 0 ? 'up' : 'down'}>{inrFull(r.pnl)}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
      {totalPages > 1 && (
        <div className="row" style={{ justifyContent: 'center', marginTop: 12, gap: 8 }}>
          <button className="btn ghost" disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}>← Prev</button>
          <span className="sub" style={{ margin: 0 }}>Page {page + 1} of {totalPages}</span>
          <button className="btn ghost" disabled={page >= totalPages - 1}
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}>Next →</button>
        </div>
      )}
    </div>
  )
}

function Dividends({ client }) {
  const [reload, setReload] = useState(0)
  const [suggestions, setSuggestions] = useState(null)
  const [suggestLoading, setSuggestLoading] = useState(false)
  const [suggestError, setSuggestError] = useState(null)
  const d = useAsync(() => api.dividends(client.id), [client.id, reload])

  async function findMissing() {
    setSuggestLoading(true)
    setSuggestError(null)
    try {
      const rows = await api.dividendSuggestions(client.id)
      setSuggestions(rows)
    } catch (e) {
      setSuggestError(e)
    } finally {
      setSuggestLoading(false)
    }
  }

  async function accept(row) {
    await api.createDividend(client.id, {
      symbol: row.symbol,
      ex_date: row.ex_date,
      amount_per_share: row.amount_per_share,
      quantity: row.estimated_quantity,
      source: 'backfill',
    })
    setSuggestions((rows) => rows.filter((r) => !(r.symbol === row.symbol && r.ex_date === row.ex_date)))
    setReload((n) => n + 1)
  }

  async function remove(id) {
    await api.deleteDividend(client.id, id)
    setReload((n) => n + 1)
  }

  if (d.loading) return <Loading what="dividends" />
  if (d.error) return <ErrorBox error={d.error} />

  const total = d.data.reduce((s, r) => s + (r.amount_per_share * r.quantity || 0), 0)

  return (
    <div>
      <p className="sub">
        Dividends recorded for this client, stored once entered — never re-fetched. Use "Find missing dividends"
        to pull suggested past dividends from market data; nothing is added until you accept a row.
      </p>
      <div className="cards" style={{ marginBottom: 16 }}>
        <Stat label="Total dividends recorded" value={inr(total)} sub={`${d.data.length} entries`} />
      </div>
      <button className="btn" onClick={findMissing} disabled={suggestLoading}>
        {suggestLoading ? 'Searching…' : 'Find missing dividends'}
      </button>
      {suggestError && <ErrorBox error={suggestError} />}
      {suggestions && (
        <div className="panel tbl-scroll" style={{ padding: 16, marginTop: 12 }}>
          <h2>Suggestions</h2>
          {!suggestions.length && <div className="empty">No new dividends found.</div>}
          {suggestions.length > 0 && (
            <table>
              <thead>
                <tr><th>Symbol</th><th>Ex-date</th><th>Per share</th><th>Est. qty</th><th>Est. total</th><th /></tr>
              </thead>
              <tbody>
                {suggestions.map((r) => (
                  <tr key={`${r.symbol}-${r.ex_date}`}>
                    <td className="mono">{r.symbol}</td>
                    <td>{r.ex_date}</td>
                    <td className="tnum">{inrFull(r.amount_per_share)}</td>
                    <td className="tnum">{r.estimated_quantity}</td>
                    <td className="tnum">{inrFull(r.estimated_total)}</td>
                    <td><button className="btn ghost" onClick={() => accept(r)}>Accept</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      <div className="panel tbl-scroll" style={{ padding: 16, marginTop: 12 }}>
        <h2>Recorded dividends</h2>
        {!d.data.length && <div className="empty">No dividends recorded yet.</div>}
        {d.data.length > 0 && (
          <table>
            <thead>
              <tr><th>Symbol</th><th>Ex-date</th><th>Per share</th><th>Qty</th><th>Total</th><th>Source</th><th /></tr>
            </thead>
            <tbody>
              {[...d.data].sort((a, b) => (a.ex_date < b.ex_date ? 1 : -1)).map((r) => (
                <tr key={r.id}>
                  <td className="mono">{r.symbol}</td>
                  <td>{r.ex_date}</td>
                  <td className="tnum">{inrFull(r.amount_per_share)}</td>
                  <td className="tnum">{r.quantity}</td>
                  <td className="tnum">{inrFull(r.amount_per_share * r.quantity)}</td>
                  <td className="sub">{r.source}</td>
                  <td><button className="btn ghost" onClick={() => remove(r.id)}>Remove</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
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
  const [page, setPage] = useState(0) // pagination
  const t = useAsync(() => api.trades(client.id, { tag: tagFilter || undefined }), [client.id, reload, tagFilter])
  const tagsQ = useAsync(() => api.tags(client.id), [client.id, reload])

  if (t.loading || tagsQ.loading) return <Loading what="trades" />
  if (t.error) return <ErrorBox error={t.error} />
  const allTags = tagsQ.data || []
  const tagsById = Object.fromEntries(allTags.map((tg) => [tg.id, tg]))
  const rows = t.data.data.filter((r) => !q || r.symbol.includes(q.toUpperCase()))

  const appliedFor = (r) => override[r.fingerprint] ?? r.tag_ids ?? []
  const pageSize = 10
  const paged = rows.slice(page * pageSize, (page + 1) * pageSize)
  const totalPages = Math.ceil(rows.length / pageSize)

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
        <input placeholder="Filter by symbol…" value={q} onChange={(e) => { setQ(e.target.value); setPage(0) }} />
        <select value={tagFilter} onChange={(e) => { setTagFilter(e.target.value); setPage(0) }}>
          <option value="">All tags</option>
          {allTags.map((tg) => <option key={tg.id} value={tg.id}>{tg.name}</option>)}
        </select>
        <span className="sub" style={{ margin: 0 }}>{rows.length} of {t.data.meta.total} trades</span>
      </div>
      <p className="sub">Why you took a trade, plus tags to categorize it — click a trade's tags to add or create one.</p>
      <div className="panel tbl-scroll">
        <table className="trades-table">
          <colgroup>
            <col style={{ width: '7%' }} /><col style={{ width: '12%' }} /><col style={{ width: '6%' }} />
            <col style={{ width: '6%' }} /><col style={{ width: '8%' }} /><col style={{ width: '11%' }} />
            <col style={{ width: '25%' }} /><col style={{ width: '25%' }} />
          </colgroup>
          <thead>
            <tr>
              <th>Date</th><th>Symbol</th><th>Type</th><th className="r">Qty</th><th className="r">Price</th><th className="r">Value</th><th>Why</th><th>Tags</th>
            </tr>
          </thead>
          <tbody>
            {paged.map((r) => {
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
      {totalPages > 1 && (
        <div className="row" style={{ justifyContent: 'center', marginTop: 12, gap: 8 }}>
          <button className="btn ghost" disabled={page === 0}
            onClick={() => { setPage((p) => Math.max(0, p - 1)); setExpanded(null) }}>← Prev</button>
          <span className="sub" style={{ margin: 0 }}>Page {page + 1} of {totalPages}</span>
          <button className="btn ghost" disabled={page >= totalPages - 1}
            onClick={() => { setPage((p) => Math.min(totalPages - 1, p + 1)); setExpanded(null) }}>Next →</button>
        </div>
      )}
    </div>
  )
}

// Every section is mounted simultaneously now (continuous-scroll dashboard), and the
// scrollspy above changes `tab` state on every scroll tick — memoize the section
// components so that state change doesn't force heavy children (charts, big tables)
// to re-render when their own props haven't changed.
const OverviewSection = React.memo(Overview)
const HoldingsSection = React.memo(Holdings)
const AllocationSection = React.memo(Allocation)
const PerformanceSection = React.memo(Performance)
const DividendsSection = React.memo(Dividends)
const TradesSection = React.memo(Trades)
