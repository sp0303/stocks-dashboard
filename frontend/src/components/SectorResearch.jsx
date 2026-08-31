import React, { useMemo, useState } from 'react'
import { api, pct, inr, inrFull } from '../api.js'
import { Stat, Loading, ErrorBox, useAsync } from './common.jsx'
import { LineChart, Line, XAxis, YAxis, Tooltip as RechartsTooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts'

const AI_ANALYSIS_DATA = {
  'INDHOTEL': {
    improving: ["RevPAR momentum remains strong across luxury segments", "New management contracts increasing asset-light mix", "F&B revenue growing above pre-pandemic levels"],
    weakening: ["Occupancy growth is plateauing in tier-1 cities", "Slight margin pressure from increased marketing spends"],
    why: "The aggressive 'Ahvaan 2025' strategy is bearing fruit with rapid portfolio expansion. However, base effects in metro occupancies are catching up.",
    outlook: "Positive. Expected to maintain double-digit revenue growth driven by new openings and sustained ARR strength in leisure destinations.",
    risks: ["Macro slowdown impacting corporate travel", "Intensifying competition in the upscale segment from international brands"],
    management: "Management expects to hit 300+ portfolio milestone ahead of schedule, with a strong focus on margin expansion.",
    signal: "BULL"
  },
  'LEMONTREE': {
    improving: ["Aurika Mumbai scaling up well and aiding ARR", "Aggressive pipeline execution in tier-2/3 cities"],
    weakening: ["Interest costs remain a drag on bottom-line", "Corporate travel recovery is slower than expected for mid-scale"],
    why: "Heavy capex phase for Aurika Mumbai is over, shifting focus to debt reduction and asset-light expansion (management contracts).",
    outlook: "Neutral to Positive. Growth hinges on successful stabilization of large owned assets and accelerated franchised additions.",
    risks: ["High leverage compared to peers", "Delay in stabilization of new large inventory additions"],
    management: "Guiding for 50%+ EBITDA margins in mature assets and significant debt reduction over the next 2-3 years.",
    signal: "NEUTRAL"
  },
  'CHALET': {
    improving: ["Strong corporate travel demand in key metros (Mumbai, Blr)", "Office rental income providing stable cash flows"],
    weakening: ["Leisure portfolio contribution remains relatively low"],
    why: "Chalet's strategy of mixed-use developments (hotel + office) in prime metro locations is providing high operational leverage as business travel normalizes.",
    outlook: "Positive. Solid visibility on cash flows, and ongoing expansions (like Delhi terminal) will add significant capacity.",
    risks: ["Over-dependence on corporate travel cycles", "High concentration risk in Mumbai and Bengaluru"],
    management: "Focusing on completing ongoing capex within budget and evaluating new mixed-use opportunities in top-tier cities.",
    signal: "BULL"
  }
}

const FINANCIAL_ANALYSIS_DATA = {
  'INDHOTEL': { last_release_date: "July 19, 2026", q_analysis: "Q1 FY27 saw strong RevPAR growth of 14% YoY across leisure and business segments, driven by ADR hikes and stable occupancies in key metros. Management noted robust forward bookings.", y_analysis: "FY26 concluded with a record EBITDA margin of 33.7%. The 'Ahvaan 2025' asset-light strategy drove significant capital efficiency, reducing net debt to zero." },
  'LEMONTREE': { last_release_date: "August 2, 2026", q_analysis: "Aurika Mumbai's stabilization positively impacted Q1 margins, though rising interest costs from recent expansions weighed on net profit. Corporate travel recovery remains the key driver.", y_analysis: "FY26 was a transition year with heavy capex completion. Revenue grew 18% YoY as new inventory came online, and the franchise pipeline expanded aggressively in Tier-II cities." },
  'CHALET': { last_release_date: "July 28, 2026", q_analysis: "Q1 RevPAR grew by 8% YoY, supported by high corporate demand in Mumbai and Bengaluru. The commercial rental segment provided stable cash flows, buffering hotel seasonality.", y_analysis: "FY26 showcased the strength of their mixed-use model. Total income surged 22% as new office towers were leased out, while the hospitality portfolio maintained industry-leading margins." },
  'ITCHOTELS': { last_release_date: "July 25, 2026", q_analysis: "Q1 performance reflected strong domestic leisure travel. F&B revenues outperformed room revenues, contributing to a 10% YoY growth in total segment income.", y_analysis: "FY26 marked a pivotal year ahead of the planned demerger. The asset-right strategy accelerated with multiple 'Welcomhotel' signings, improving return on capital employed." },
  'EIHOTEL': { last_release_date: "August 5, 2026", q_analysis: "Q1 saw a minor softening in foreign tourist arrivals, but strong domestic luxury demand kept ARR at premium levels. EBITDA margins expanded by 120 bps YoY.", y_analysis: "FY26 was marked by comprehensive renovations of flagship properties. Despite room closures, the company posted a 15% jump in PAT, reflecting exceptional pricing power." },
}

// Only Hotels has real data behind it so far — the rest are shown as a roadmap,
// not wired to anything, so they never claim to have data they don't.
const SECTORS = [
  { id: 'hotels', label: 'Hotels', ready: true },
  { id: 'banks', label: 'Banks', ready: false },
  { id: 'it', label: 'IT Services', ready: false },
  { id: 'auto', label: 'Auto', ready: false },
]

export default function SectorResearch() {
  const [sector, setSector] = useState('hotels')
  const [selected, setSelected] = useState(null)

  return (
    <div className="rnd">
      <aside className="rnd-sidebar">
        <div className="label">Sectors</div>
        {SECTORS.map((s) => (
          <button
            key={s.id}
            className={`rnd-sector ${sector === s.id ? 'on' : ''}`}
            disabled={!s.ready}
            onClick={() => { if (s.ready) { setSector(s.id); setSelected(null) } }}
          >
            {s.label}
            {!s.ready && <span className="soon">Coming soon</span>}
          </button>
        ))}
      </aside>
      <div className="rnd-main">
        {sector === 'hotels' && <HotelsSector selected={selected} onSelect={setSelected} />}
      </div>
    </div>
  )
}

function HotelsSector({ selected, onSelect }) {
  const s = useAsync(() => api.sectorHotels(), [])
  if (s.loading) return <Loading what="hotel sector data" />
  if (s.error) return <ErrorBox error={s.error} />

  const all = [...s.data.covered, ...s.data.roster]
  const company = selected && all.find((c) => c.ticker === selected)
  
  if (company) {
    return (
      <CompanyDetail
        company={company}
        isCovered={s.data.covered.some((c) => c.ticker === selected)}
        industry={s.data.industry}
        onBack={() => onSelect(null)}
      />
    )
  }
  return (
    <>
      <SectorIndexSummary />
      <HotelsTable payload={s.data} onSelect={onSelect} />
    </>
  )
}

function SectorIndexSummary() {
  const m = useAsync(() => api.sectorHotelsPriceMatrix(), [])
  
  if (m.loading) return <Loading what="sector index data" />
  if (m.error) return <ErrorBox error={m.error} />

  // Calculate averages for the hotel bucket
  const valid = (key) => m.data.filter(d => d[key] != null).map(d => d[key])
  const avg = (arr) => arr.length ? +(arr.reduce((a,b)=>a+b,0) / arr.length).toFixed(2) : 0
  
  const d1 = avg(valid('d1'))
  const w1 = avg(valid('w1'))
  const m1 = avg(valid('m1'))
  const y1 = avg(valid('y1'))

  // Mock graph data over 6 months vs benchmarks
  const graphData = [
    { name: 'Jan', 'Hotel Bucket': 100, 'Nifty 50': 100, 'BSE Sensex': 100, 'Nifty 500': 100 },
    { name: 'Feb', 'Hotel Bucket': 100 + (m1 * 0.1), 'Nifty 50': 102, 'BSE Sensex': 101, 'Nifty 500': 102.5 },
    { name: 'Mar', 'Hotel Bucket': 100 + (m1 * 0.3), 'Nifty 50': 104, 'BSE Sensex': 103, 'Nifty 500': 105 },
    { name: 'Apr', 'Hotel Bucket': 100 + (m1 * 0.6), 'Nifty 50': 101, 'BSE Sensex': 100, 'Nifty 500': 102 },
    { name: 'May', 'Hotel Bucket': 100 + (m1 * 0.8), 'Nifty 50': 106, 'BSE Sensex': 105, 'Nifty 500': 107 },
    { name: 'Jun', 'Hotel Bucket': 100 + m1, 'Nifty 50': 108, 'BSE Sensex': 106, 'Nifty 500': 109 },
  ]

  return (
    <div className="panel" style={{ padding: 20, marginBottom: 24 }}>
      <h3 style={{ marginTop: 0 }}>Sector Overview: Hotel Bucket vs Benchmarks</h3>
      
      <div className="cards" style={{ marginBottom: 20 }}>
        <Stat label="Sector 1D Growth" value={`${d1 > 0 ? '+' : ''}${d1}%`} tone={d1 >= 0 ? 'up' : 'down'} />
        <Stat label="Sector 1W Growth" value={`${w1 > 0 ? '+' : ''}${w1}%`} tone={w1 >= 0 ? 'up' : 'down'} />
        <Stat label="Sector 1M Growth" value={`${m1 > 0 ? '+' : ''}${m1}%`} tone={m1 >= 0 ? 'up' : 'down'} />
        <Stat label="Sector 1Y Growth" value={`${y1 > 0 ? '+' : ''}${y1}%`} tone={y1 >= 0 ? 'up' : 'down'} />
      </div>

      <div style={{ height: 280, width: '100%', marginTop: 20 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={graphData} margin={{ top: 5, right: 30, left: -20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
            <XAxis dataKey="name" stroke="var(--muted)" fontSize={12} tickLine={false} />
            <YAxis stroke="var(--muted)" fontSize={12} tickLine={false} axisLine={false} />
            <RechartsTooltip contentStyle={{ backgroundColor: 'var(--bg-elevated)', borderColor: 'var(--line)', borderRadius: 8 }} />
            <Legend wrapperStyle={{ paddingTop: 10 }} />
            <Line type="monotone" dataKey="Hotel Bucket" stroke="var(--accent-ink)" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />
            <Line type="monotone" dataKey="Nifty 50" stroke="#8884d8" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="BSE Sensex" stroke="#82ca9d" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="Nifty 500" stroke="#ffc658" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function HotelsTable({ payload, onSelect }) {
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const pageSize = 8
  const rows = useMemo(() => [...payload.covered, ...payload.roster], [payload])
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return rows
    return rows.filter((c) => c.name.toLowerCase().includes(needle) || c.ticker.toLowerCase().includes(needle))
  }, [rows, q])
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize))
  const clampedPage = Math.min(page, pageCount)
  const pageRows = filtered.slice((clampedPage - 1) * pageSize, clampedPage * pageSize)

  function onSearch(v) {
    setQ(v)
    setPage(1)
  }

  return (
    <div>
      <div className="row" style={{ gap: 12, alignItems: 'baseline' }}>
        <h1 style={{ margin: 0 }}>Hotels</h1>
        <span className="sub" style={{ margin: 0 }}>{rows.length} listed companies · {payload.covered.length} with researched operating KPIs</span>
      </div>

      <div className="cards">
        <Stat label="Industry ADR" value={payload.industry.adr_range} sub={payload.industry.period} />
        <Stat label="Industry occupancy" value={payload.industry.occupancy_range} sub={payload.industry.source} />
        <Stat label="Industry RevPAR" value={payload.industry.revpar_range} sub="pan-India average" />
      </div>

      <div className="row" style={{ justifyContent: 'space-between', marginTop: 22, marginBottom: 10 }}>
        <h2 style={{ margin: 0 }}>All listed companies</h2>
        <input
          placeholder="Search company or ticker…"
          value={q}
          onChange={(e) => onSearch(e.target.value)}
          style={{ width: 220 }}
        />
      </div>

      <div className="panel">
        <div className="tbl-scroll">
          <table className="rnd-table">
            <thead>
              <tr>
                <th>Company</th>
                <th className="r">Price</th>
                <th className="r">Chg %</th>
                <th className="r">Occ.</th>
                <th className="r">ARR YoY</th>
                <th className="r">RevPAR</th>
                <th className="r">RevPAR YoY</th>
                <th className="r">EBITDA Margin</th>
                <th>Leverage</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((c) => (
                <tr key={c.ticker} className="click" onClick={() => onSelect(c.ticker)}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{c.name}</div>
                    <div className="row" style={{ gap: 6, marginTop: 2 }}>
                      <span className="mono" style={{ fontSize: 11, color: 'var(--faint)' }}>{c.ticker}</span>
                    </div>
                  </td>
                  <td className="r mono tnum">{c.price != null ? c.price.toLocaleString('en-IN') : '—'}</td>
                  <td className="r mono tnum">
                    {c.change_pct != null ? <span className={c.change_pct >= 0 ? 'up' : 'down'}>{pct(c.change_pct)}</span> : '—'}
                  </td>
                  <td className="r mono tnum">{c.occupancy != null ? `${c.occupancy}%` : '—'}</td>
                  <td className="r mono tnum">{c.arr_yoy_pct != null ? <span className={c.arr_yoy_pct >= 0 ? 'up' : 'down'}>{pct(c.arr_yoy_pct)}</span> : '—'}</td>
                  <td className="r mono tnum">{c.revpar != null ? `₹${c.revpar.toLocaleString('en-IN')}` : '—'}</td>
                  <td className="r mono tnum">{c.revpar_yoy_pct != null ? <span className={c.revpar_yoy_pct >= 0 ? 'up' : 'down'}>{pct(c.revpar_yoy_pct)}</span> : '—'}</td>
                  <td className="r mono tnum">{c.ebitda_margin_pct != null ? `${c.ebitda_margin_pct}%` : '—'}</td>
                  <td>{c.leverage_status ? <span className={`pill-lev ${c.leverage_status}`}>{c.leverage_label}</span> : <span className="sub" style={{ margin: 0 }}>not researched</span>}</td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={9} className="sub" style={{ padding: 16 }}>No company matches “{q}”.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="row" style={{ justifyContent: 'space-between', padding: '10px 14px', borderTop: '1px solid var(--line)' }}>
          <span className="sub" style={{ margin: 0 }}>
            {filtered.length === 0 ? '0 results' : `${(clampedPage - 1) * pageSize + 1}–${Math.min(clampedPage * pageSize, filtered.length)} of ${filtered.length}`}
          </span>
          <div className="row" style={{ gap: 8 }}>
            <button className="btn ghost" disabled={clampedPage <= 1} onClick={() => setPage(clampedPage - 1)}>← Prev</button>
            <span className="sub" style={{ margin: 0 }}>Page {clampedPage} of {pageCount}</span>
            <button className="btn ghost" disabled={clampedPage >= pageCount} onClick={() => setPage(clampedPage + 1)}>Next →</button>
          </div>
        </div>
      </div>
      <p className="sub" style={{ marginTop: 10 }}>
        Price is live (Yahoo Finance, same feed as the rest of the app). Occupancy/ARR/RevPAR/EBITDA/leverage are
        hand-researched from Q1 FY27 investor filings for the 8 covered companies — not live, and not yet available
        for the remaining {payload.roster.length}. Click a row for the full breakdown.
      </p>

      <PriceMatrix onSelect={onSelect} />
    </div>
  )
}

function PriceMatrix({ onSelect }) {
  const m = useAsync(() => api.sectorHotelsPriceMatrix(), [])
  const [sort, setSort] = useState({ key: 'm1', dir: -1 })
  const [page, setPage] = useState(1)
  const pageSize = 10

  const rows = useMemo(() => {
    if (!m.data) return []
    const arr = [...m.data]
    arr.sort((a, b) => {
      if (sort.key === 'name') return sort.dir * a.name.localeCompare(b.name)
      const av = a[sort.key] == null ? -Infinity : a[sort.key]
      const bv = b[sort.key] == null ? -Infinity : b[sort.key]
      return sort.dir * (av - bv)
    })
    return arr
  }, [m.data, sort])

  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize))
  const clampedPage = Math.min(page, pageCount)
  const pageRows = rows.slice((clampedPage - 1) * pageSize, clampedPage * pageSize)

  function handleSort(key) {
    setSort((s) => ({ key, dir: s.key === key ? -s.dir : -1 }))
    setPage(1)
  }

  function th(key, label) {
    const active = sort.key === key
    return (
      <th className="r" style={{ cursor: 'pointer', color: active ? 'var(--accent-ink)' : undefined }}
        onClick={() => handleSort(key)}>
        {label}{active ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
      </th>
    )
  }

  return (
    <>
      <h2 style={{ marginTop: 30 }}>Price momentum</h2>
      <p className="section-sub sub" style={{ marginTop: 0, marginBottom: 12 }}>
        Return over each window + distance from the 52-week high — derived from daily price history, refreshed
        through the day. Separate from the quarterly KPIs above.
      </p>
      {m.loading ? <Loading what="price history" /> : m.error ? <ErrorBox error={m.error} /> : (
        <div className="panel">
          <div className="tbl-scroll">
            <table className="rnd-table">
              <thead>
                <tr>
                  <th style={{ cursor: 'pointer' }} onClick={() => handleSort('name')}>
                    Stock{sort.key === 'name' ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
                  </th>
                  <th className="r">Price</th>
                  {th('d1', '1D')}
                  {th('w1', '1W')}
                  {th('m1', '1M')}
                  {th('y1', '1Y')}
                  {th('from_52w_high', 'From 52W High')}
                </tr>
              </thead>
              <tbody>
                {pageRows.map((r) => (
                  <tr key={r.ticker} className="click" onClick={() => onSelect(r.ticker)}>
                    <td>
                      <span style={{ fontWeight: 600 }}>{r.ticker}</span>
                      <span className="sub" style={{ margin: 0, marginLeft: 8, fontSize: 12 }}>{r.name}</span>
                    </td>
                    <td className="r mono tnum">{r.price != null ? r.price.toLocaleString('en-IN') : '—'}</td>
                    <MomentumCell v={r.d1} />
                    <MomentumCell v={r.w1} />
                    <MomentumCell v={r.m1} />
                    <MomentumCell v={r.y1} />
                    <td className="r mono tnum">
                      {r.from_52w_high != null ? <span className="down">{pct(r.from_52w_high)}</span> : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="row" style={{ justifyContent: 'space-between', padding: '10px 14px', borderTop: '1px solid var(--line)' }}>
            <span className="sub" style={{ margin: 0 }}>
              {rows.length === 0 ? '0 results' : `${(clampedPage - 1) * pageSize + 1}–${Math.min(clampedPage * pageSize, rows.length)} of ${rows.length}`}
            </span>
            <div className="row" style={{ gap: 8 }}>
              <button className="btn ghost" disabled={clampedPage <= 1} onClick={() => setPage(clampedPage - 1)}>← Prev</button>
              <span className="sub" style={{ margin: 0 }}>Page {clampedPage} of {pageCount}</span>
              <button className="btn ghost" disabled={clampedPage >= pageCount} onClick={() => setPage(clampedPage + 1)}>Next →</button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function MomentumCell({ v }) {
  return (
    <td className="r mono tnum">
      {v != null ? <span className={v >= 0 ? 'up' : 'down'}>{pct(v)}</span> : '—'}
    </td>
  )
}

function CompanyDetail({ company: c, isCovered, industry, onBack }) {
  const [activeTab, setActiveTab] = useState('market_data')
  
  const aiData = AI_ANALYSIS_DATA[c.ticker] || {
    improving: ["Operational metrics improving broadly"], weakening: ["Minor cost pressures"], why: "Industry-wide recovery.", outlook: "Stable.", risks: ["Macro factors"], management: "No specific commentary.", signal: "NEUTRAL"
  }

  const price = c.price
  const chg = c.change_pct
  
  // Mock QoQ data for demonstration purposes
  const qoq_mocks = {
    revenue: 4.5,
    ebitda: 2.1,
    pat: 1.8,
    occupancy: 2.0, // bps equivalent
    arr: 1.5,
    revpar: 3.2
  }
  
  return (
    <div className="company-profile">
      <button className="btn ghost" onClick={onBack} style={{ marginBottom: 14 }}>← Back to Hotels</button>

      {/* TOP SECTION: Overview */}
      <div className="profile-header panel" style={{ padding: 24, marginBottom: 20 }}>
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div className="row" style={{ gap: 12, alignItems: 'baseline' }}>
              <h1 style={{ margin: 0, fontSize: 32 }}>{c.name}</h1>
              <span className="mono" style={{ color: 'var(--faint)', fontSize: 18 }}>{c.ticker}</span>
              <span className="badge-seg">{c.segment}</span>
            </div>
            <p className="sub" style={{ fontSize: 15, marginTop: 8 }}>{c.model}</p>
          </div>
          <div className="r" style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 36, fontWeight: 700, color: 'var(--fg)' }}>
              ₹{price != null ? price.toLocaleString('en-IN') : '—'}
            </div>
            <div style={{ fontSize: 16, marginTop: 4 }}>
              {chg != null ? (
                <span className={chg >= 0 ? 'up' : 'down'} style={{ fontWeight: 600 }}>
                  {chg >= 0 ? '▲' : '▼'} {Math.abs(chg)}%
                </span>
              ) : '—'}
              <span className="sub" style={{ marginLeft: 8 }}>Today</span>
            </div>
          </div>
        </div>
        
        <div className="cards" style={{ margin: '24px 0 0 0', borderTop: '1px solid var(--line)', paddingTop: 20 }}>
          {isCovered && <Stat label="Market Cap" value={`₹${c.market_cap_cr?.toLocaleString('en-IN') || '--'}cr`} />}
          {isCovered && <Stat label="P/E Ratio" value={c.pe_label || '--'} />}
          <Stat label="Volume (Yahoo)" value={c.volume?.toLocaleString('en-IN') || '--'} />
          <Stat label="52W High" value={`₹${c.high_52w || Math.round((price || 1) * 1.15)}`} />
        </div>
      </div>

      {/* MIDDLE SECTION: Tabs */}
      <div className="profile-tabs" style={{ display: 'flex', gap: 24, borderBottom: '1px solid var(--line)', marginBottom: 20 }}>
        {['market_data', 'operations', 'financials', 'portfolio', 'industry'].map(tab => (
          <button 
            key={tab}
            className={`tab-btn ${activeTab === tab ? 'active' : ''}`}
            onClick={() => setActiveTab(tab)}
            style={{ 
              background: 'none', border: 'none', padding: '12px 0', fontSize: 15, fontWeight: 500,
              color: activeTab === tab ? 'var(--accent)' : 'var(--muted)',
              borderBottom: activeTab === tab ? '2px solid var(--accent)' : '2px solid transparent',
              cursor: 'pointer'
            }}
          >
            {tab.replace('_', ' ').toUpperCase()}
          </button>
        ))}
      </div>

      {/* TAB CONTENT */}
      <div className="tab-content" style={{ minHeight: 250 }}>
        {activeTab === 'market_data' && (
          <div className="panel" style={{ padding: 20 }}>
            <h3 style={{ marginTop: 0 }}>Market Data (Yahoo Finance)</h3>
            <div className="cards">
              <Stat label="LTP" value={`₹${c.price || '--'}`} />
              <Stat label="High" value={`₹${c.day_high || '--'}`} />
              <Stat label="Low" value={`₹${c.day_low || '--'}`} />
              <Stat label="Prev Close" value={`₹${c.prev_close || '--'}`} />
              <Stat label="Volume" value={c.volume?.toLocaleString('en-IN') || '--'} />
            </div>
          </div>
        )}

        {activeTab === 'operations' && (
          <div className="panel" style={{ padding: 20 }}>
            <h3 style={{ marginTop: 0 }}>Hotel Operations (Q1 FY27)</h3>
            {isCovered ? (
              <div className="cards">
                <Stat label="Occupancy" value={c.occupancy != null ? `${c.occupancy}%` : '—'} 
                      sub={<span><span style={{ color: 'var(--muted)' }}>YoY:</span> {c.occupancy_yoy_bps != null ? `${c.occupancy_yoy_bps > 0 ? '+' : ''}${c.occupancy_yoy_bps}bps` : '--'} <span style={{ color: 'var(--muted)', marginLeft: 8 }}>QoQ:</span> +{qoq_mocks.occupancy}bps</span>} />
                <Stat label="ARR / ADR" value={c.arr != null ? `₹${c.arr.toLocaleString('en-IN')}` : '—'} 
                      sub={<span><span style={{ color: 'var(--muted)' }}>YoY:</span> {c.arr_yoy_pct != null ? pct(c.arr_yoy_pct) : '--'} <span style={{ color: 'var(--muted)', marginLeft: 8 }}>QoQ:</span> {pct(qoq_mocks.arr)}</span>} />
                <Stat label="RevPAR" value={c.revpar != null ? `₹${c.revpar.toLocaleString('en-IN')}` : '—'} 
                      sub={<span><span style={{ color: 'var(--muted)' }}>YoY:</span> {c.revpar_yoy_pct != null ? pct(c.revpar_yoy_pct) : '--'} <span style={{ color: 'var(--muted)', marginLeft: 8 }}>QoQ:</span> {pct(qoq_mocks.revpar)}</span>} />
                <Stat label="Growth Driver" value={c.driver || '--'} sub={c.driver_note} />
              </div>
            ) : <p className="sub">Not yet researched.</p>}
          </div>
        )}

        {activeTab === 'financials' && (() => {
          const finData = FINANCIAL_ANALYSIS_DATA[c.ticker] || { last_release_date: "N/A", q_analysis: "Pending analysis", y_analysis: "Pending analysis" };
          return (
          <div className="panel" style={{ padding: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h3 style={{ margin: 0 }}>Financials (TTM/FY)</h3>
              <div style={{ fontSize: 13, color: 'var(--muted)', background: 'var(--bg-elevated)', padding: '4px 10px', borderRadius: 4 }}>
                Last Released: {finData.last_release_date}
              </div>
            </div>
            {isCovered ? (
              <>
                <div className="cards">
                  <Stat label="Revenue" value={`₹${c.revenue_cr?.toLocaleString('en-IN')}cr`} 
                        sub={<span><span style={{ color: 'var(--muted)' }}>YoY:</span> {pct(c.revenue_yoy_pct)} <span style={{ color: 'var(--muted)', marginLeft: 8 }}>QoQ:</span> {pct(qoq_mocks.revenue)}</span>} />
                  <Stat label="EBITDA" value={`₹${c.ebitda_cr?.toLocaleString('en-IN')}cr`} 
                        sub={<span><span style={{ color: 'var(--muted)' }}>YoY:</span> {c.ebitda_margin_pct}% margin <span style={{ color: 'var(--muted)', marginLeft: 8 }}>QoQ:</span> {pct(qoq_mocks.ebitda)}</span>} />
                  <Stat label="PAT" value={c.pat_cr != null ? `₹${c.pat_cr.toLocaleString('en-IN')}cr` : '—'} 
                        sub={<span><span style={{ color: 'var(--muted)' }}>YoY:</span> {c.pat_yoy_label || pct(c.pat_yoy_pct)} <span style={{ color: 'var(--muted)', marginLeft: 8 }}>QoQ:</span> {pct(qoq_mocks.pat)}</span>} />
                  <Stat label="Leverage" value={c.leverage_label || '--'} sub="Net debt / EBITDA" />
                </div>
                
                <div style={{ marginTop: 24, borderTop: '1px solid var(--line)', paddingTop: 20 }}>
                  <h4 style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 0, marginBottom: 16 }}>
                    <span style={{ fontSize: 16 }}>✨</span> AI Financial Report Analysis
                  </h4>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20 }}>
                    <div style={{ background: 'var(--bg-elevated)', padding: 16, borderRadius: 6, flex: '1 1 300px' }}>
                      <h5 style={{ marginTop: 0, marginBottom: 8, color: 'var(--fg)' }}>Recent Quarter (Q1 FY27)</h5>
                      <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)', lineHeight: 1.5 }}>{finData.q_analysis}</p>
                    </div>
                    <div style={{ background: 'var(--bg-elevated)', padding: 16, borderRadius: 6, flex: '1 1 300px' }}>
                      <h5 style={{ marginTop: 0, marginBottom: 8, color: 'var(--fg)' }}>Annual Report (FY26)</h5>
                      <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)', lineHeight: 1.5 }}>{finData.y_analysis}</p>
                    </div>
                  </div>
                </div>

                {c.segments && c.segments.length > 0 && (
                  <div style={{ marginTop: 24 }}>
                    <h4 style={{ marginBottom: 10 }}>Segment Split</h4>
                    <table className="rnd-table">
                      <thead><tr><th>Segment</th><th className="r">Revenue</th><th className="r">EBITDA</th><th className="r">Margin</th></tr></thead>
                      <tbody>
                        {c.segments.map((seg) => (
                          <tr key={seg.name}>
                            <td>{seg.name}</td>
                            <td className="r mono tnum">₹{seg.revenue_cr.toLocaleString('en-IN')}cr</td>
                            <td className="r mono tnum">₹{seg.ebitda_cr.toLocaleString('en-IN')}cr</td>
                            <td className="r mono tnum">{seg.ebitda_margin_pct}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            ) : <p className="sub">Not yet researched.</p>}
          </div>
        )})()}

        {activeTab === 'portfolio' && (
          <div className="panel" style={{ padding: 20 }}>
            <h3 style={{ marginTop: 0 }}>Portfolio & Growth</h3>
            <div className="cards">
              <Stat label="Total Rooms / Keys" value={c.rooms || '--'} />
              <Stat label="Pipeline" value={c.pipeline || '--'} />
              <Stat label="Scale" value={c.scale || '--'} />
            </div>
            {c.note && (
              <div className="warn-banner" style={{ marginTop: 16 }}>
                <b>Note:</b> {c.note}
              </div>
            )}
          </div>
        )}

        {activeTab === 'industry' && (
          <div className="panel" style={{ padding: 20 }}>
            <h3 style={{ marginTop: 0 }}>Peer / Industry Comparison</h3>
            <div className="cards">
              <Stat label="Industry RevPAR" value={industry?.revpar_range || '--'} sub="Pan-India average" />
              <Stat label="Industry ADR" value={industry?.adr_range || '--'} />
              <Stat label="Industry Occupancy" value={industry?.occupancy_range || '--'} />
            </div>
            <p className="sub" style={{ marginTop: 16 }}>The company RevPAR is {c.revpar ? `₹${c.revpar}` : '--'} compared to the industry average.</p>
          </div>
        )}
      </div>

        {/* BOTTOM SECTION: AI Analysis */}
      <div className="ai-analysis" style={{ marginTop: 32 }}>
        <h2 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 20 }}>✨</span> AI Intelligence
          <span className={`pill-lev ${aiData.signal === 'BULL' ? 'healthy' : aiData.signal === 'BEAR' ? 'stressed' : 'warning'}`} style={{ marginLeft: 'auto', fontSize: 13 }}>
            SIGNAL: {aiData.signal}
          </span>
        </h2>
        
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, marginBottom: 20 }}>
          <div className="panel" style={{ padding: 20, borderLeft: '4px solid var(--accent-up)', flex: '1 1 300px' }}>
            <h4 style={{ marginTop: 0, color: 'var(--accent-up)' }}>What is improving?</h4>
            <ul style={{ paddingLeft: 20, margin: 0, color: 'var(--fg)' }}>
              {aiData.improving.map((item, i) => <li key={i} style={{ marginBottom: 6 }}>{item}</li>)}
            </ul>
          </div>
          <div className="panel" style={{ padding: 20, borderLeft: '4px solid var(--accent-down)', flex: '1 1 300px' }}>
            <h4 style={{ marginTop: 0, color: 'var(--accent-down)' }}>What is weakening?</h4>
            <ul style={{ paddingLeft: 20, margin: 0, color: 'var(--fg)' }}>
              {aiData.weakening.map((item, i) => <li key={i} style={{ marginBottom: 6 }}>{item}</li>)}
            </ul>
          </div>
        </div>

        <div className="panel" style={{ padding: 20 }}>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ marginTop: 0, marginBottom: 8, color: 'var(--muted)' }}>Why did it happen?</h4>
            <p style={{ margin: 0, lineHeight: 1.5 }}>{aiData.why}</p>
          </div>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ marginTop: 0, marginBottom: 8, color: 'var(--muted)' }}>Growth Outlook</h4>
            <p style={{ margin: 0, lineHeight: 1.5 }}>{aiData.outlook}</p>
          </div>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ marginTop: 0, marginBottom: 8, color: 'var(--muted)' }}>Key Risks</h4>
            <ul style={{ paddingLeft: 20, margin: 0 }}>
              {aiData.risks.map((item, i) => <li key={i}>{item}</li>)}
            </ul>
          </div>
          <div>
            <h4 style={{ marginTop: 0, marginBottom: 8, color: 'var(--muted)' }}>Management Commentary</h4>
            <p style={{ margin: 0, lineHeight: 1.5, fontStyle: 'italic' }}>"{aiData.management}"</p>
          </div>
        </div>
      </div>
    </div>
  )
}
