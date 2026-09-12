import React, { useState, useRef, useEffect } from 'react'
import {
  PieChart, Pie, Cell, Sector, ResponsiveContainer, Tooltip, LineChart, Line, XAxis, YAxis, CartesianGrid, ReferenceLine,
  BarChart, Bar, Area, ComposedChart, Legend,
} from 'recharts'
import { api, inr, inrFull, pct, pctPlain } from '../api.js'
import { Stat, PnL, PctPnL, Loading, ErrorBox, useAsync, PALETTE } from './common.jsx'
import StockAnalysis from './StockAnalysis.jsx'
import Watchlist from './Watchlist.jsx'
import { CorporateActionsFeed } from './CorporateActions.jsx'
import { AccountSelector } from './AccountSelector.jsx'
import { AccountManager } from './AccountManager.jsx'
import { PortfolioViewer } from './PortfolioViewer.jsx'


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


function SubNav({ sections, sectionRefs, activeSection }) {
  const scrollToSection = (sectionKey) => {
    const el = document.getElementById(`section-${sectionKey}`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  return (
    <div style={{ background: 'var(--bg)', overflowX: 'auto', padding: '0 1.5rem 0.5rem' }}>
      <div style={{ display: 'flex', gap: '0.5rem', minWidth: 'min-content' }}>
        {sections.map((s) => (
          <button
            key={s.key}
            onClick={() => scrollToSection(s.key)}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: 999,
              border: '1px solid var(--line)',
              background: activeSection === s.key ? 'var(--accent)' : 'transparent',
              color: activeSection === s.key ? 'white' : 'var(--ink)',
              fontWeight: activeSection === s.key ? 600 : 400,
              cursor: 'pointer',
              fontSize: '0.875rem',
              whiteSpace: 'nowrap',
            }}
          >
            {s.label}
          </button>
        ))}
      </div>
    </div>
  )
}

export default function ClientDashboard({ client }) {
  const [reload, setReload] = useState(0)
  const [symbol, setSymbol] = useState(null) // drilled into a single stock
  const [searchHoldings, setSearchHoldings] = useState('')
  const [activeSection, setActiveSection] = useState('upload')
  const sectionRefs = useRef({})
  const observerRef = useRef(null)

  const sections = [
    { key: 'upload', label: 'Upload' },
    { key: 'overview', label: 'Overview' },
    { key: 'portfolio-viewer', label: 'Portfolio Sync' },
    { key: 'holdings', label: 'Holdings' },
    { key: 'allocation', label: 'Allocation' },
    { key: 'performance', label: 'Performance' },
    { key: 'trade-analytics', label: 'Trade Analytics' },
    { key: 'dividends', label: 'Dividends' },
    { key: 'playbook', label: 'Playbook' },
    { key: 'corp-actions', label: 'Corporate Actions' },
    { key: 'watchlist', label: 'Watchlist' },
    { key: 'kite-accounts', label: 'Kite Accounts' },
  ]

  useEffect(() => {
    if (observerRef.current) observerRef.current.disconnect()

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            const sectionKey = entry.target.id.replace('section-', '')
            setActiveSection(sectionKey)
            break
          }
        }
      },
      { threshold: 0.3 }
    )

    sections.forEach((s) => {
      const el = document.getElementById(`section-${s.key}`)
      if (el) observer.observe(el)
    })

    observerRef.current = observer
    return () => observer.disconnect()
  }, [])

  if (symbol) {
    return <StockAnalysis client={client} symbol={symbol} onBack={() => setSymbol(null)} />
  }

  return (
    <div>
      {/* STICKY HEADER + SUB-NAV as one unit, so the tab bar never hides behind the
          taller title (the old bug: title ~4.75rem tall but the nav stuck at top:3.5rem). */}
      <div style={{ position: 'sticky', top: 0, background: 'var(--bg)', zIndex: 10, borderBottom: '1px solid var(--line)' }}>
        <div style={{ padding: '0.55rem 1.5rem 0.35rem' }}>
          <h1 style={{ margin: 0, fontSize: '1.2rem', lineHeight: 1.2 }}>{client.name}</h1>
          <p className="sub mono" style={{ margin: '0.1rem 0 0 0', fontSize: '0.78rem' }}>{client.client_code || 'no broker code'}</p>
        </div>
        <SubNav sections={sections} sectionRefs={sectionRefs} activeSection={activeSection} />
      </div>

      {/* UNIFIED SCROLLABLE DASHBOARD — full width with modest side gutters */}
      <div style={{ maxWidth: '1760px', margin: '0 auto', padding: '1rem 1.5rem' }}>
        <AISummaryCard client={client} reload={reload} />

        {/* ALL SECTIONS VISIBLE - NO TABS */}
        <Section sectionKey="upload" title="Upload Tradebook" sectionRef={(el) => (sectionRefs.current.upload = el)}>
          <UploadBar client={client} onDone={() => setReload((n) => n + 1)} />
        </Section>

        <Section sectionKey="overview" title="Overview" sectionRef={(el) => (sectionRefs.current.overview = el)}>
          <OverviewSection client={client} reload={reload} onChanged={() => setReload((n) => n + 1)} />
        </Section>

        <Section sectionKey="portfolio-viewer" title="Portfolio Sync" sectionRef={(el) => (sectionRefs.current['portfolio-viewer'] = el)}>
          <PortfolioViewer clientId={client.id} />
        </Section>

        <Section sectionKey="holdings" title="Holdings" sectionRef={(el) => (sectionRefs.current.holdings = el)}>
          <HoldingsSection client={client} reload={reload} onOpenStock={setSymbol} />
        </Section>

        <Section sectionKey="allocation" title="Allocation" sectionRef={(el) => (sectionRefs.current.allocation = el)}>
          <AllocationSection client={client} reload={reload} />
        </Section>

        <Section sectionKey="performance" title="Performance" sectionRef={(el) => (sectionRefs.current.performance = el)}>
          <PerformanceSection client={client} reload={reload} onOpenStock={setSymbol} />
        </Section>

        <Section sectionKey="trade-analytics" title="Trade Analytics" sectionRef={(el) => (sectionRefs.current['trade-analytics'] = el)}>
          <TradeAnalyticsSection client={client} reload={reload} />
        </Section>

        <Section sectionKey="dividends" title="Dividends" sectionRef={(el) => (sectionRefs.current.dividends = el)}>
          <DividendsSection client={client} />
        </Section>

        <Section sectionKey="playbook" title="Playbook" sectionRef={(el) => (sectionRefs.current.playbook = el)}>
          <PlaybookSection client={client} reload={reload} />
        </Section>

        <Section sectionKey="corp-actions" title="Corporate Actions" sectionRef={(el) => (sectionRefs.current['corp-actions'] = el)}>
          <CorporateActionsFeed client={client} />
        </Section>

        <Section sectionKey="watchlist" sectionRef={(el) => (sectionRefs.current.watchlist = el)}>
          <Watchlist scope="clients" id={client.id} title="Client watchlist" />
        </Section>

        <Section sectionKey="kite-accounts" title="Kite Account Management" sectionRef={(el) => (sectionRefs.current['kite-accounts'] = el)}>
          <AccountManager clientId={client.id} onAccountAdded={() => setReload((n) => n + 1)} />
        </Section>
      </div>
    </div>
  )
}


function UploadBar({ client, onDone }) {
  const inputRef = useRef()
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)
  const [mode, setMode] = useState('kite') // 'kite' or 'manual'
  const [kiteApiKey, setKiteApiKey] = useState('')
  const [kiteAccessToken, setKiteAccessToken] = useState('')
  const [reloadAccounts, setReloadAccounts] = useState(0)
  const t = useAsync(() => api.trades(client.id), [client.id, onDone])
  const kiteStatus = useAsync(() => api.kiteStatus(client.id), [client.id])

  async function connectKite() {
    if (!kiteApiKey || !kiteAccessToken) {
      setMsg({ ok: false, text: 'Please enter Kite API Key and Access Token' })
      return
    }
    setBusy(true); setMsg(null)
    try {
      const r = await api.kiteAuthenticate(client.id, {
        api_key: kiteApiKey,
        access_token: kiteAccessToken,
      })
      setMsg({ ok: true, text: `Connected! User: ${r.user_name}` })
      setKiteApiKey('')
      setKiteAccessToken('')
    } catch (e) {
      setMsg({ ok: false, text: e.message })
    } finally {
      setBusy(false)
    }
  }

  async function syncKiteTrades() {
    setBusy(true); setMsg(null)
    try {
      const r = await api.kiteSyncTrades(client.id)
      setMsg({ ok: true, text: `Synced! Imported ${r.imported} trades. Cash: ₹${(r.cash / 1e5).toFixed(2)}L` })
      onDone()
    } catch (e) {
      setMsg({ ok: false, text: e.message })
    } finally {
      setBusy(false)
    }
  }

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

  // Calculate date range from trades
  const trades = t.data?.data || []
  let earliestDate = null
  let latestDate = null
  let daysOld = null

  if (trades.length > 0) {
    const dates = trades.map(t => new Date(t.trade_date)).sort((a, b) => a - b)
    earliestDate = dates[0]
    latestDate = dates[dates.length - 1]
    const today = new Date()
    daysOld = Math.floor((today - latestDate) / (1000 * 60 * 60 * 24))
  }

  const formatDate = (d) => d?.toLocaleDateString('en-IN', { year: 'numeric', month: 'short', day: 'numeric' })

  return (
    <div className="panel" style={{ padding: 14, marginTop: 8 }}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center' }}>
        <div style={{ flex: 1 }}>
          <button onClick={() => setMode('kite')} style={{ padding: '6px 12px', background: mode === 'kite' ? 'var(--up)' : 'transparent', border: '1px solid var(--line)', cursor: 'pointer', fontWeight: mode === 'kite' ? 'bold' : 'normal' }}>🔗 Kite API</button>
          <button onClick={() => setMode('manual')} style={{ padding: '6px 12px', marginLeft: 8, background: mode === 'manual' ? 'var(--up)' : 'transparent', border: '1px solid var(--line)', cursor: 'pointer', fontWeight: mode === 'manual' ? 'bold' : 'normal' }}>📤 Manual Upload</button>
        </div>
        <AccountSelector clientId={client.id} onAccountChange={() => setReloadAccounts((n) => n + 1)} />
      </div>

      {mode === 'kite' ? (
        <div>
          <strong>Kite Account Management</strong>
          <div className="sub" style={{ margin: 0, marginBottom: 12 }}>Manage your Kite accounts above. Use manual upload for other trade sources.</div>
        </div>
      ) : (
        <div>
          <strong>Manual Kite Tradebook Upload</strong>
          <div className="sub" style={{ margin: 0 }}>Zerodha equity export (.xlsx). Re-uploads dedupe automatically.</div>
          <div className="sub" style={{ margin: '8px 0 0 0', fontSize: 12, color: 'var(--muted)' }}>
            📊 Market data (LTP, prices) from Angel One
          </div>
          {earliestDate && latestDate && (
            <div className="sub" style={{ margin: '8px 0 0 0', fontSize: 12, color: 'var(--muted)' }}>
              Trades: <strong>{formatDate(earliestDate)}</strong> to <strong>{formatDate(latestDate)}</strong>
              {daysOld > 0 && (
                <span style={{ color: daysOld > 30 ? 'var(--down)' : 'var(--muted)', marginLeft: 8 }}>
                  ({daysOld} days old)
                </span>
              )}
            </div>
          )}
          <div style={{ marginTop: 12 }}>
            <input ref={inputRef} type="file" accept=".xlsx,.xls" onChange={(e) => upload(e.target.files[0])} disabled={busy} />
          </div>
        </div>
      )}

      {busy && <div className="loading" style={{ padding: '8px 0 0' }}>Processing…</div>}
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
  const [showThinking, setShowThinking] = useState(false)
  if (n.error) return null // quietly omit — the rest of the dashboard doesn't depend on this
  const lines = n.data?.narrative ? splitNarrative(n.data.narrative) : []
  const thinking = n.data?.thinking
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
        <>
          {thinking && (
            <div className="ai-thinking">
              <button type="button" className="ai-thinking-toggle" onClick={() => setShowThinking((v) => !v)}>
                {showThinking ? '▾' : '▸'} Thinking
              </button>
              {showThinking && <div className="ai-thinking-body">{thinking}</div>}
            </div>
          )}
          <ul>
            {lines.map((line, i) => <NarrativeLine key={i} text={line} />)}
          </ul>
        </>
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
      {[['current', 'Current holdings'], ['invested', 'All ever invested']].map(([k, label]) => (
        <button key={k} className={basis === k ? 'on' : ''} onClick={() => setBasis(k)} title={k === 'current' ? 'What you own now' : 'All stocks ever traded (open + closed)'}>{label}</button>
      ))}
    </div>
  )
}

// Pie + legend table, hover-synced both ways: hovering a table row (or a slice)
// enlarges that slice and dims the rest so it's unambiguous which is which.
function AllocationChart({ data, height = 300, outerRadius = 110, innerRadius = 55, labelKey = 'key' }) {
  const [hover, setHover] = useState(null)
  const [sort, setSort] = useState({ key: 'value', dir: 'desc' })

  const toggleSort = (key) => {
    setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }))
  }

  const sorted = [...data].sort((a, b) => {
    const av = a[sort.key], bv = b[sort.key]
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    if (typeof av === 'string') return sort.dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av)
    return sort.dir === 'asc' ? av - bv : bv - av
  })

  // Map sorted array back to original indices for hover-sync with pie chart
  const hoverRow = hover !== null ? sorted[hover] : null
  const origIdx = hoverRow ? data.findIndex((r) => r.key === hoverRow.key) : null

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
              activeIndex={origIdx !== null ? origIdx : undefined}
              activeShape={renderActiveSlice}
              onMouseEnter={(_, i) => setHover(data.findIndex((r) => r.key === sorted[data.findIndex((x) => x.key === data[i].key)].key))}
              onMouseLeave={() => setHover(null)}
            >
              {data.map((_, i) => (
                <Cell
                  key={i}
                  fill={PALETTE[i % PALETTE.length]}
                  fillOpacity={origIdx === null || origIdx === i ? 1 : 0.35}
                />
              ))}
            </Pie>
            <Tooltip formatter={(v, n, item) => [`${inrFull(v)} (${item.payload.pct}%)`, n]} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="panel tbl-scroll">
        <table>
          <thead><tr><th style={{ cursor: 'pointer', userSelect: 'none' }} onClick={() => toggleSort('key')}>{labelKey}{sort.key === 'key' ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}</th><th className="r" style={{ cursor: 'pointer', userSelect: 'none' }} onClick={() => toggleSort('value')}>Value{sort.key === 'value' ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}</th><th className="r" style={{ cursor: 'pointer', userSelect: 'none' }} onClick={() => toggleSort('pct')}>Weight{sort.key === 'pct' ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}</th></tr></thead>
          <tbody>
            {sorted.map((r, i) => (
              <tr key={r.key} className={hover === i ? 'hl' : ''} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                <td><span className="dot" style={{ background: PALETTE[data.findIndex((x) => x.key === r.key) % PALETTE.length] }} />{r.key}</td>
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

// Inline fixer inside the unmatched-sell banner: add the acquisition cost (an
// opening BUY) for an IPO/bonus/pre-window share so it stops being excluded.
function OpeningTradeFixer({ client, symbols, onChanged }) {
  const [sym, setSym] = useState(symbols[0] || '')
  const [qty, setQty] = useState('')
  const [price, setPrice] = useState('')
  const [date, setDate] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  async function add(e) {
    e.preventDefault()
    if (!sym || !qty || price === '') { setErr('Fill symbol, quantity and price'); return }
    setBusy(true); setErr(null)
    try {
      await api.addManualTrade(client.id, {
        symbol: sym, trade_type: 'buy', quantity: Number(qty), price: Number(price),
        trade_date: date || new Date().toISOString().slice(0, 10), note: 'acquisition cost (opening buy)',
      })
      setQty(''); setPrice(''); setDate('')
      onChanged?.()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <form className="row" onSubmit={add} style={{ gap: 8, marginTop: 10, flexWrap: 'wrap', alignItems: 'center' }}>
      <select value={sym} onChange={(e) => setSym(e.target.value)}>
        {symbols.map((s) => <option key={s} value={s}>{s}</option>)}
      </select>
      <input type="number" step="any" min="0" placeholder="Qty" value={qty} style={{ width: 90 }}
        onChange={(e) => setQty(e.target.value)} />
      <input type="number" step="any" min="0" placeholder="Cost ₹/share" value={price} style={{ width: 120 }}
        onChange={(e) => setPrice(e.target.value)} />
      <input type="date" value={date} title="Acquisition date (optional)" onChange={(e) => setDate(e.target.value)} />
      <button className="btn" disabled={busy}>Add cost</button>
      {err && <span className="err" style={{ fontSize: 12 }}>⚠ {err}</span>}
    </form>
  )
}

// Lists opening/adjustment trades added by hand, with a remove control. Only renders
// when there are any, so it stays out of the way for clean tradebooks.
function ManualTradesPanel({ client, onChanged }) {
  const [reload, setReload] = useState(0)
  const m = useAsync(() => api.manualTrades(client.id), [client.id, reload])
  const rows = m.data || []
  if (m.loading || !rows.length) return null

  async function remove(fp) {
    await api.deleteManualTrade(client.id, fp)
    setReload((n) => n + 1)
    onChanged?.()
  }

  return (
    <div className="panel" style={{ padding: 12, marginBottom: 12 }}>
      <div className="sub" style={{ margin: '0 0 6px' }}>
        Manual opening/adjustment trades (not from the tradebook — IPO/bonus/pre-window):
      </div>
      <table>
        <thead><tr><th>Date</th><th>Symbol</th><th>Type</th><th className="r">Qty</th><th className="r">Price</th><th>Note</th><th></th></tr></thead>
        <tbody>
          {rows.map((t) => (
            <tr key={t.fingerprint}>
              <td className="sub">{t.trade_date}</td>
              <td style={{ fontWeight: 600 }}>{t.symbol}</td>
              <td>{t.trade_type}</td>
              <td className="r tnum">{t.quantity}</td>
              <td className="r tnum">{inrFull(t.price)}</td>
              <td className="sub">{t.note}</td>
              <td className="r">
                <button className="btn ghost" style={{ padding: '3px 9px' }} onClick={() => remove(t.fingerprint)}>Remove</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TargetAlerts({ alerts }) {
  if (!alerts || alerts.length === 0) return null
  const fmt = (a) => a.metric === 'price' ? `₹${a.current} / ₹${a.target_value}` : `${a.current}% / ${a.target_value}%`
  return (
    <div style={{
      border: '1px solid var(--line)', borderLeft: '4px solid var(--accent)',
      borderRadius: 8, padding: '14px 16px', marginBottom: 18, background: 'var(--surface-2)',
    }}>
      <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
        🎯 Targets to check <span style={{ color: 'var(--muted)', fontWeight: 400 }}>({alerts.length})</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {alerts.map((a, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, flexWrap: 'wrap' }}>
            <span style={{
              fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 4,
              background: a.status === 'hit' ? 'var(--up, #0f7a5a)' : '#c9820a', color: '#fff',
            }}>{a.status === 'hit' ? 'TARGET HIT' : 'NEAR'}</span>
            <strong>{a.symbol}</strong>
            <span style={{ color: 'var(--muted)' }}>{a.target_type}</span>
            <span className="tnum">{fmt(a)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function Overview({ client, reload, onChanged }) {
  const [basis, setBasis] = useState('current')

  // CRITICAL: Load immediately
  const p = useAsync(() => api.portfolio(client.id), [client.id, reload])
  const m = useAsync(() => api.metrics(client.id), [client.id, reload])

  // DEFERRED: Load after critical content renders for better perceived performance
  const c = useAsync(() => api.concentration(client.id), [client.id, reload])
  const alloc = useAsync(() => api.allocation(client.id, 'sector', basis), [client.id, reload, basis])
  const rm = useAsync(() => api.riskMonitoring(client.id), [client.id, reload])
  const alerts = useAsync(() => api.thesisAlerts(client.id), [client.id, reload])
  if (p.loading) return <Loading what="portfolio" />
  if (p.error) return <ErrorBox error={p.error} />
  const d = p.data
  if (!d.total_trades) return <div className="empty">No trades yet. Upload a tradebook above to see the portfolio.</div>

  // Calculate holding period
  const getHoldingPeriod = () => {
    if (!d.first_trade_date || !d.last_trade_date) return ''
    const start = new Date(d.first_trade_date)
    const end = new Date(d.last_trade_date)
    let years = 0, months = 0, days = 0

    days = end.getDate() - start.getDate()
    if (days < 0) {
      months--
      const prevMonth = new Date(end.getFullYear(), end.getMonth(), 0)
      days += prevMonth.getDate()
    }

    months += end.getMonth() - start.getMonth()
    if (months < 0) {
      years--
      months += 12
    }

    years += end.getFullYear() - start.getFullYear()

    const parts = []
    if (years > 0) parts.push(`${years}y`)
    if (months > 0) parts.push(`${months}m`)
    if (days > 0) parts.push(`${days}d`)
    return parts.join(' ') || '0d'
  }

  return (
    <div>
      <TargetAlerts alerts={alerts.data} />
      <div className="cards">
        <Stat label="Market Value" value={inr(d.market_value)} sub={inrFull(d.market_value)} />
        <Stat label="Deployed Capital" value={inr(d.initial_capital)} sub={inrFull(d.initial_capital)} title="External capital deployed (buys - sells)" />
        <Stat label="Current Invested" value={inr(d.current_invested)} sub={inrFull(d.current_invested)} title="Cost basis of current holdings" />
        <Stat label="Total P&L" value={inr(d.total_pnl)} tone={d.total_pnl >= 0 ? 'up' : 'down'} sub={`${pct(d.return_pct)} over ${getHoldingPeriod()}`} />
        <Stat label="Realized P&L" value={inr(d.realized_pnl)} tone={d.realized_pnl >= 0 ? 'up' : 'down'} />
        <Stat label="Unrealized P&L" value={inr(d.unrealized_pnl)} tone={d.unrealized_pnl >= 0 ? 'up' : 'down'} />
        <Stat label="Open positions" value={d.open_positions} sub={`${d.total_trades} trades`} />
        <Stat label="Last trade date" value={d.last_trade_date ? d.last_trade_date : '—'} sub="most recent trade" />
      </div>
      {!m.loading && !m.error && m.data && (
        <div className="cards" style={{ marginTop: '1rem' }}>
          <Stat label="CAGR" value={m.data.cagr != null ? pct(m.data.cagr * 100) : '—'} sub="annualized" title="Compound Annual Growth Rate" />
          <Stat label="Sharpe Ratio" value={m.data.sharpe_ratio ? m.data.sharpe_ratio.toFixed(2) : '—'} sub="risk-adjusted" title="Return per unit of risk (>1 is good)" />
          <Stat label="Volatility" value={m.data.volatility ? pct(m.data.volatility) : '—'} sub="annual" title="Standard deviation of returns" />
          <Stat label="Max Drawdown" value={m.data.max_drawdown != null ? pct(m.data.max_drawdown * 100) : '—'} tone="down" sub="peak-to-trough" />
          <Stat label="Beta" value={m.data.beta ? m.data.beta.toFixed(3) : '—'} sub="vs Nifty 50" title="1.0 = moves with market" />
          <Stat label="Alpha" value={m.data.alpha ? (m.data.alpha >= 0 ? '+' : '') + pct(m.data.alpha) : '—'} tone={m.data.alpha >= 0 ? 'up' : 'down'} sub="vs benchmark" title="Excess return after risk adjustment" />
        </div>
      )}
      {!rm.loading && !rm.error && rm.data && !rm.data.error && (
        <>
          <h2>Portfolio Health</h2>
          <div className="cards">
            <Stat label="Health Score" value={rm.data.health_score || '—'} sub={`${rm.data.health_score || 0}/100`} title="Risk concentration & volatility assessment" />
            <Stat label="Top 10 Holdings" value={pctPlain(rm.data.concentration?.top_10_pct)} sub="of portfolio" title="Concentration in largest 10 positions" />
            <Stat label="Largest Sector" value={rm.data.concentration?.largest_sector} sub={pctPlain(rm.data.concentration?.largest_sector_pct)} />
            <Stat label="Total Positions" value={rm.data.total_positions} sub="open holdings" />
          </div>
          {rm.data.alerts && rm.data.alerts.size > 0 && (
            <div style={{ padding: '1rem', background: 'var(--bg-alt)', borderRadius: '4px', marginTop: '1rem' }}>
              <strong>⚠ Risk Alerts:</strong>
              <ul style={{ marginTop: '0.5rem', paddingLeft: '1.5rem' }}>
                {Array.from(rm.data.alerts).map((alert) => (
                  <li key={alert}>{alert}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
      {d.unpriced_symbols && d.unpriced_symbols.length > 0 && (
        <div className="warn-banner">
          No live price for {d.unpriced_symbols.join(', ')} ({inrFull(d.unpriced_invested)} invested) —
          excluded from Market Value, Unrealized P&L, and the totals above.
        </div>
      )}
      {d.unmatched_sell_symbols && d.unmatched_sell_symbols.length > 0 && (
        <div className="warn-banner">
          {d.unmatched_sell_symbols.join(', ')} {d.unmatched_sell_symbols.length > 1 ? 'were' : 'was'} sold with
          no matching buy in the tradebook ({inrFull(d.unmatched_sell_value)} of proceeds) — likely an IPO
          allotment, bonus, or a buy from before the tradebook window. Its cost basis is unknown, so this is
          excluded from Realized P&amp;L rather than counted as pure profit. Add the acquisition cost below to include it.
          <OpeningTradeFixer client={client} symbols={d.unmatched_sell_symbols} onChanged={onChanged} />
        </div>
      )}
      <ManualTradesPanel client={client} onChanged={onChanged} />
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
          <AllocationChart data={alloc.data.filter(a => a.key !== 'Unclassified')} height={260} outerRadius={95} innerRadius={45} labelKey="Sector" />
          {alloc.data.some(a => a.key === 'Unclassified') && (
            <div className="warn-banner" style={{ marginTop: 12 }}>
              ⚠ {inrFull(alloc.data.find(a => a.key === 'Unclassified')?.value)} in unclassified sectors — update your watchlist sector assignments
            </div>
          )}
        </>
      )}
    </div>
  )
}

const PLAYBOOK_STOCK_COLUMNS = [
  { key: 'symbol', label: 'Stock' },
  { key: 'trades_count', label: 'Trades', r: true },
  { key: 'total_qty', label: 'Total Qty', r: true },
  { key: 'avg_buy_price', label: 'Avg Buy', r: true },
  { key: 'avg_sell_price', label: 'Avg Sell', r: true },
  { key: 'avg_days', label: 'Avg Days', r: true },
  { key: 'total_pnl', label: 'PNL', r: true },
  { key: 'pnl_pct', label: 'PNL %', r: true },
]

// Round-trip (bought-then-sold) trade history, FIFO-matched on the backend,
// collapsed one row per stock (weighted-avg buy/sell price, total P&L). Click a
// stock to see its individual closed lots in a detail modal.
const PLAYBOOK_PAGE_SIZE = 10

function Playbook({ client, reload }) {
  // The whole playbook, then the same by-stock view sliced by how long trades were held:
  // intraday (same-day) and within a week — each in the identical pattern.
  return (
    <div>
      <PlaybookByStockTable client={client} reload={reload}
        intro="Closed round trips, merged stock-wise — weighted-average buy/sell price and total P&L. Click a stock for its individual lots. Click a column to sort." />
      <h3 style={{ margin: '30px 0 4px' }}>Intraday</h3>
      <PlaybookByStockTable client={client} reload={reload} intraday
        intro="Stocks bought & sold the same day, merged stock-wise (speculative per Section 43(5))."
        emptyMsg="No intraday (same-day) trades." />
      <h3 style={{ margin: '30px 0 4px' }}>Within a week</h3>
      <PlaybookByStockTable client={client} reload={reload} minDays={1} maxDays={7}
        intro="Positions held 1–7 days, merged stock-wise."
        emptyMsg="No trades held within a week." />
    </div>
  )
}

function PlaybookByStockTable({ client, reload, minDays, maxDays, intraday, intro, emptyMsg }) {
  const [sort, setSort] = useState({ key: 'total_pnl', dir: 'desc' })
  const [page, setPage] = useState(0)
  const [openSymbol, setOpenSymbol] = useState(null)
  const pb = useAsync(() => api.playbookByStock(client.id, { minDays, maxDays, intraday }),
    [client.id, reload, minDays, maxDays, intraday])
  const rows = pb.data || []

  // back to the first page whenever the sort or the underlying data changes
  useEffect(() => { setPage(0) }, [sort, rows])

  function toggleSort(key) {
    setSort((cur) => (cur.key === key ? { key, dir: cur.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }))
  }
  const sorted = [...rows].sort((a, b) => {
    const av = a[sort.key], bv = b[sort.key]
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    if (typeof av === 'string') return sort.dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av)
    return sort.dir === 'asc' ? av - bv : bv - av
  })
  const totalPages = Math.ceil(sorted.length / PLAYBOOK_PAGE_SIZE)
  const paged = sorted.slice(page * PLAYBOOK_PAGE_SIZE, page * PLAYBOOK_PAGE_SIZE + PLAYBOOK_PAGE_SIZE)

  return (
    <div>
      <p className="sub">{intro}</p>
      {pb.loading && <Loading what="playbook" />}
      {pb.error && <ErrorBox error={pb.error} />}
      {!pb.loading && !pb.error && !rows.length && (
        <div className="empty">{emptyMsg || 'No closed trades yet.'}</div>
      )}
      {!pb.loading && !pb.error && rows.length > 0 && (
        <div className="panel tbl-scroll">
          <table>
            <thead>
              <tr>
                {PLAYBOOK_STOCK_COLUMNS.map((c) => (
                  <th key={c.key} className={c.r ? 'r click' : 'click'} onClick={() => toggleSort(c.key)}>
                    {c.label}{sort.key === c.key ? (sort.dir === 'desc' ? ' ▾' : ' ▴') : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {paged.map((r) => (
                <tr key={r.symbol} className="click" onClick={() => setOpenSymbol(r.symbol)}>
                  <td style={{ fontWeight: 600, color: 'var(--accent-ink)' }}>{r.symbol}</td>
                  <td className="r tnum">{r.trades_count}</td>
                  <td className="r tnum">{r.total_qty}</td>
                  <td className="r tnum">{r.avg_buy_price}</td>
                  <td className="r tnum">{r.avg_sell_price}</td>
                  <td className="r tnum">{r.avg_days ?? '—'}</td>
                  <td className="r tnum">{r.total_pnl != null ? <span className={r.total_pnl >= 0 ? 'up' : 'down'}>{inrFull(r.total_pnl)}</span> : '—'}</td>
                  <td className="r tnum"><PctPnL value={r.pnl_pct} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {totalPages > 1 && (
        <div className="row" style={{ justifyContent: 'center', marginTop: 12, gap: 8 }}>
          <button className="btn ghost" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>← Prev</button>
          <span className="sub" style={{ margin: 0 }}>Page {page + 1} of {totalPages}</span>
          <button className="btn ghost" disabled={page >= totalPages - 1} onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}>Next →</button>
        </div>
      )}
      {openSymbol && <PlaybookStockModal client={client} symbol={openSymbol} onClose={() => setOpenSymbol(null)} />}
    </div>
  )
}

const PLAYBOOK_DETAIL_COLUMNS = [
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

// Modal (reuses the drawer overlay pattern) showing every individual closed lot
// for one stock — the rows the stock-wise table above collapsed into one line.
function PlaybookStockModal({ client, symbol, onClose }) {
  const d = useAsync(
    () => api.playbook(client.id, { symbol, sort: 'sell_date', order: 'desc', pageSize: 200 }),
    [client.id, symbol]
  )
  const rows = d.data?.data || []

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <div style={{ fontWeight: 700, fontSize: 18 }}>{symbol}</div>
          <button className="close" onClick={onClose} aria-label="Close">×</button>
        </div>
        <div className="drawer-body">
          {d.loading && <Loading what="lots" />}
          {d.error && <ErrorBox error={d.error} />}
          {!d.loading && !d.error && (
            <div className="panel tbl-scroll">
              <table>
                <thead>
                  <tr>{PLAYBOOK_DETAIL_COLUMNS.map((c) => <th key={c.key} className={c.r ? 'r' : ''}>{c.label}</th>)}</tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i}>
                      <td className="r tnum">{r.quantity}</td>
                      <td className="r tnum">{r.buy_price}</td>
                      <td>{r.buy_date}</td>
                      <td className="r tnum">{r.sell_price}</td>
                      <td>{r.sell_date}</td>
                      <td className="r tnum">{r.days ?? '—'}</td>
                      <td className="r tnum">{r.pnl != null ? <span className={r.pnl >= 0 ? 'up' : 'down'}>{inrFull(r.pnl)}</span> : '—'}</td>
                      <td className="r tnum"><PctPnL value={r.pnl_pct} /></td>
                      <td>{r.reason || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
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
              <td style={{ fontWeight: 600, color: 'var(--accent-ink)' }}>{r.symbol}{r.price_unavailable ? <span className="stale" title="No live price — excluded from totals">no price</span> : r.stale && <span className="stale">stale</span>}</td>
              <td className="r tnum">{r.quantity}{r.applied_actions && r.applied_actions.length > 0 && (
                <span className="ca-badge" title={`Quantity adjusted for: ${r.applied_actions.map((a) => `${a.type} ×${a.multiplier} on ${a.ex_date}`).join('; ')}`}>adj</span>
              )}</td>
              <td className="r tnum">{r.avg_cost}</td>
              <td className="r tnum">{r.ltp ?? '—'}</td>
              <td className="r tnum">{inrFull(r.invested_value)}</td>
              <td className="r tnum">{inrFull(r.market_value)}</td>
              <td className="r tnum">{r.unrealized_pnl != null ? <span className={r.unrealized_pnl >= 0 ? 'up' : 'down'}>{inrFull(r.unrealized_pnl)}</span> : '—'}</td>
              <td className="r tnum"><PctPnL value={r.unrealized_pct} /></td>
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

function Performance({ client, reload, onOpenStock }) {
  const p = useAsync(() => api.performance(client.id), [client.id, reload])
  const x = useAsync(() => api.xirr(client.id), [client.id, reload])
  const [benchmarks, setBenchmarks] = useState({
    nifty_50: true,
    mid_cap: true,
    large_cap: false,
    small_cap: false,
  })

  if (p.loading) return <Loading what="performance" />
  if (p.error) return <ErrorBox error={p.error} />
  if (!p.data.length) return <div className="empty">No history yet.</div>

  const toggleBenchmark = (key) => {
    setBenchmarks((cur) => ({ ...cur, [key]: !cur[key] }))
  }

  const benchmarkColors = {
    total_value: '#1e40af',
    nifty_50: '#dc2626',
    mid_cap: '#ea580c',
    large_cap: '#8b5cf6',
    small_cap: '#059669',
  }

  const benchmarkLabels = {
    total_value: 'Your Portfolio',
    nifty_50: 'Nifty 50',
    mid_cap: 'Nifty Midcap 100',
    large_cap: 'Nifty 100 (Large Cap)',
    small_cap: 'Nifty Smallcap 100',
  }

  // Each benchmark_{key}_value is already an absolute rupee amount: what the SAME
  // buy/sell cash flows (same dates, same amounts) would be worth today had they gone
  // into that index instead of your stocks — computed server-side from real index
  // prices. So it's directly comparable to total_value with no rescaling here.
  const rawData = p.data
  const startValue = rawData[0]?.total_value ?? ((rawData[0]?.invested_value || 0) + (rawData[0]?.realized_pnl || 0))
  const lastRaw = rawData[rawData.length - 1]
  const endValue = lastRaw?.total_value ?? ((lastRaw?.invested_value || 0) + (lastRaw?.realized_pnl || 0))
  const absoluteGain = endValue - startValue

  // The chart itself plots PROFIT/LOSS, not raw value — an absolute-value line conflates
  // "money you've deposited" with "how it performed" (every new buy makes the line jump,
  // even with zero return), which read as broken/confusing. Subtracting invested_value
  // from every line (portfolio and each benchmark) removes the deposit-timing noise and
  // leaves pure gain/loss — all lines start near ₹0 and diverge only on real performance.
  const data = rawData.map((d) => ({
    ...d,
    pnl: d.total_value - d.invested_value,
    nifty_50_pnl: d.nifty_50_value != null ? d.nifty_50_value - d.invested_value : null,
    mid_cap_pnl: d.mid_cap_value != null ? d.mid_cap_value - d.invested_value : null,
    large_cap_pnl: d.large_cap_value != null ? d.large_cap_value - d.invested_value : null,
    small_cap_pnl: d.small_cap_value != null ? d.small_cap_value - d.invested_value : null,
  }))

  return (
    <div>
      <p className="sub">Profit or loss over time — yours vs. what the same money would have made in each index. The line is pure gain/loss, not raw value, so it isn't inflated by new deposits.</p>
      {!x.loading && !x.error && (
        <div className="cards" style={{ marginBottom: 16 }}>
          <Stat
            label="XIRR"
            value={pct(x.data?.xirr != null ? x.data.xirr * 100 : null)}
            sub={x.data?.xirr != null ? 'money-weighted, incl. dividends' : 'not computable — very short, high-return round trips push the required rate off the chart'}
          />
          <Stat label="CAGR" value={pct(x.data?.cagr != null ? x.data.cagr * 100 : null)} sub="invested → market value" />
          <Stat label="Portfolio growth" value={inr(absoluteGain)} tone={absoluteGain >= 0 ? 'up' : 'down'} sub={`from ${inr(startValue)} → ${inr(endValue)}`} />
        </div>
      )}

      <div className="panel" style={{ padding: 16 }}>
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 10, fontSize: 13 }}>Select benchmarks to compare:</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
            {Object.entries(benchmarks).map(([key, checked]) => (
              <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 13 }}>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleBenchmark(key)}
                  style={{ cursor: 'pointer' }}
                />
                <span style={{ color: benchmarkColors[key], fontWeight: 500 }}>
                  {benchmarkLabels[key]}
                </span>
              </label>
            ))}
          </div>
        </div>

        <ResponsiveContainer width="100%" height={380}>
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--muted)' }} minTickGap={40} />
            <YAxis
              tick={{ fontSize: 11, fill: 'var(--muted)' }}
              label={{ value: 'Profit / Loss (₹)', angle: -90, position: 'insideLeft', offset: 10 }}
              width={85}
              tickFormatter={(v) => (v >= 0 ? inr(v) : `-${inr(-v)}`)}
            />
            <Tooltip
              formatter={(v) => (Number(v) >= 0 ? inr(Number(v)) : `-${inr(-Number(v))}`)}
              labelFormatter={(label) => `${label}`}
              contentStyle={{ background: 'var(--surface)', border: '1px solid var(--line)', fontSize: 12 }}
            />
            <ReferenceLine y={0} stroke="var(--muted)" strokeDasharray="2 2" />
            <Line type="monotone" dataKey="pnl" name="Your Portfolio" stroke={benchmarkColors.total_value} dot={false} strokeWidth={2.5} connectNulls />
            {benchmarks.nifty_50 && (
              <Line type="monotone" dataKey="nifty_50_pnl" name="Nifty 50" stroke={benchmarkColors.nifty_50} dot={false} strokeWidth={2} strokeDasharray="4 3" connectNulls />
            )}
            {benchmarks.mid_cap && (
              <Line type="monotone" dataKey="mid_cap_pnl" name="Nifty Midcap 100" stroke={benchmarkColors.mid_cap} dot={false} strokeWidth={2} connectNulls />
            )}
            {benchmarks.large_cap && (
              <Line type="monotone" dataKey="large_cap_pnl" name="Nifty 100 (Large Cap)" stroke={benchmarkColors.large_cap} dot={false} strokeWidth={2} strokeDasharray="4 3" connectNulls />
            )}
            {benchmarks.small_cap && (
              <Line type="monotone" dataKey="small_cap_pnl" name="Nifty Smallcap 100" stroke={benchmarkColors.small_cap} dot={false} strokeWidth={2} connectNulls />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

// ── Trade Analytics: equity curve, win/loss stats, P&L distribution, timing ──────────
const UP = 'var(--up, #0f7a5a)'
const DOWN = 'var(--down, #c0392b)'
const AX = { fontSize: 11, fill: 'var(--muted)' }
const TT = { background: 'var(--surface)', border: '1px solid var(--line)', fontSize: 12 }
const money = (v) => (Number(v) >= 0 ? inr(Number(v)) : `-${inr(-Number(v))}`)

function MiniTradeTable({ rows, tone }) {
  if (!rows || !rows.length) return null
  return (
    <table className="ledger" style={{ width: '100%', fontSize: 13 }}>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td style={{ fontWeight: 600 }}>{r.symbol}</td>
            <td className="r tnum" style={{ color: tone === 'up' ? UP : DOWN, fontWeight: 500 }}>{money(r.pnl)}</td>
            <td className="r tnum" style={{ color: 'var(--muted)' }}>{r.pnl_pct >= 0 ? '+' : ''}{r.pnl_pct}%</td>
            <td className="r tnum" style={{ color: 'var(--muted)' }}>{r.days}d</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function WinRateTable({ rows, keyField }) {
  if (!rows || !rows.length) return <div className="sub">No data.</div>
  return (
    <table className="ledger" style={{ width: '100%', fontSize: 13 }}>
      <thead><tr><th style={{ textAlign: 'left' }}>{keyField === 'day' ? 'Day' : 'Held'}</th><th className="r">Trades</th><th className="r">Win %</th><th className="r">P&L</th></tr></thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td>{r[keyField]}</td>
            <td className="r tnum">{r.trades}</td>
            <td className="r tnum" style={{ fontWeight: 600, color: r.win_rate >= 50 ? UP : 'var(--ink)' }}>{r.win_rate}%</td>
            <td className="r tnum" style={{ color: r.pnl >= 0 ? UP : DOWN }}>{money(r.pnl)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function TradeAnalytics({ client, reload }) {
  const a = useAsync(() => api.tradeAnalytics(client.id), [client.id, reload])
  if (a.loading) return <Loading />
  if (a.error) return <ErrorBox error={a.error} />
  const d = a.data
  if (!d || d.error || !d.total_trades) return <div className="empty">No closed trades yet — upload a tradebook to see trade analytics.</div>

  return (
    <div>
      {/* 1 · Win / loss stats */}
      <div className="cards">
        <Stat label="Win rate" value={`${d.win_rate}%`} sub={`${d.winning_trades}W / ${d.losing_trades}L`} tone={d.win_rate >= 50 ? 'up' : ''} />
        <Stat label="Profit factor" value={d.profit_factor ?? '—'} tone={(d.profit_factor || 0) >= 1 ? 'up' : 'down'} />
        <Stat label="Expectancy / trade" value={money(d.expectancy)} tone={d.expectancy >= 0 ? 'up' : 'down'} />
        <Stat label="Avg win" value={inr(d.avg_win)} tone="up" />
        <Stat label="Avg loss" value={`-${inr(d.avg_loss)}`} tone="down" />
        <Stat label="Avg holding" value={`${d.avg_holding_days}d`} />
        <Stat label="Total realized" value={money(d.total_pnl)} tone={d.total_pnl >= 0 ? 'up' : 'down'} />
        <Stat label="Closed trades" value={d.total_trades} />
      </div>

      {/* 2 · Equity curve + drawdown */}
      <h4 style={{ margin: '22px 0 6px' }}>Equity curve — cumulative realized P&L</h4>
      <div className="sub" style={{ marginBottom: 8 }}>Every closed trade in sequence; the shaded band is the drawdown from the running peak.</div>
      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={d.equity_curve} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
          <XAxis dataKey="date" tick={AX} minTickGap={60} />
          <YAxis tick={AX} width={82} tickFormatter={money} />
          <Tooltip formatter={money} contentStyle={TT} />
          <ReferenceLine y={0} stroke="var(--muted)" strokeDasharray="2 2" />
          <Area type="monotone" dataKey="drawdown" name="Drawdown" stroke={DOWN} fill={DOWN} fillOpacity={0.14} strokeWidth={1} />
          <Line type="monotone" dataKey="cum_pnl" name="Cumulative P&L" stroke="var(--accent)" dot={false} strokeWidth={2.5} />
        </ComposedChart>
      </ResponsiveContainer>

      {/* 3 · Distribution + best/worst */}
      <div className="grid2" style={{ marginTop: 22 }}>
        <div>
          <h4 style={{ margin: '0 0 6px' }}>P&L distribution (by return %)</h4>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={d.distribution} margin={{ top: 8, right: 8, bottom: 30, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
              <XAxis dataKey="bucket" tick={{ ...AX, fontSize: 10 }} interval={0} angle={-35} textAnchor="end" height={48} />
              <YAxis tick={AX} width={36} allowDecimals={false} />
              <Tooltip contentStyle={TT} formatter={(v, n, p) => [`${v} trades · ${money(p.payload.pnl)}`, p.payload.bucket]} />
              <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                {d.distribution.map((b, i) => <Cell key={i} fill={i < 4 ? DOWN : UP} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div>
          <h4 style={{ margin: '0 0 6px' }}>Top winners</h4>
          <MiniTradeTable rows={d.top_winners} tone="up" />
          <h4 style={{ margin: '14px 0 6px' }}>Top losers</h4>
          <MiniTradeTable rows={d.top_losers} tone="down" />
        </div>
      </div>

      {/* 4 · Timing */}
      <h4 style={{ margin: '22px 0 6px' }}>Monthly P&L</h4>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={d.monthly_pnl} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
          <XAxis dataKey="month" tick={AX} minTickGap={24} />
          <YAxis tick={AX} width={82} tickFormatter={money} />
          <Tooltip contentStyle={TT} formatter={(v, n, p) => [`${money(v)} · ${p.payload.trades} trades · ${p.payload.win_rate}% win`, p.payload.month]} />
          <ReferenceLine y={0} stroke="var(--muted)" />
          <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
            {d.monthly_pnl.map((m, i) => <Cell key={i} fill={m.pnl >= 0 ? UP : DOWN} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <div className="grid2" style={{ marginTop: 18 }}>
        <div>
          <h4 style={{ margin: '0 0 6px' }}>By weekday (exit)</h4>
          <WinRateTable rows={d.by_weekday} keyField="day" />
        </div>
        <div>
          <h4 style={{ margin: '0 0 6px' }}>By holding period</h4>
          <WinRateTable rows={d.by_holding} keyField="bucket" />
        </div>
      </div>
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

// Every section is mounted simultaneously now (continuous-scroll dashboard), and the
// scrollspy above changes `tab` state on every scroll tick — memoize the section
// components so that state change doesn't force heavy children (charts, big tables)
// to re-render when their own props haven't changed.
const OverviewSection = React.memo(Overview)
const HoldingsSection = React.memo(Holdings)
const AllocationSection = React.memo(Allocation)
const PerformanceSection = React.memo(Performance)
const TradeAnalyticsSection = React.memo(TradeAnalytics)
const DividendsSection = React.memo(Dividends)
const PlaybookSection = React.memo(Playbook)
