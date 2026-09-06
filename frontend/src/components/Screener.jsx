import React, { useState, useEffect } from 'react'
import { api } from '../api.js'
import { Loading, ErrorBox, useAsync } from './common.jsx'

// Standalone swing-trade screener at /screener. Deliberately not linked into the main
// dashboard UI. Read-only, decision-support: shows momentum, relative strength, RSI and
// volume for the covered sector universe and ranks them — it makes no recommendation.

const SECTOR_LABELS = { hotels: 'Hotels', banks: 'Banking / BFSI', it: 'IT Services', auto: 'Automotive' }

const pctCls = (v) => (v == null ? '' : v > 0 ? 'up' : v < 0 ? 'down' : '')
const fmtPct = (v) => (v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(1)}%`)
const fmtVol = (v) => {
  if (v == null) return '—'
  if (v >= 1e7) return `${(v / 1e7).toFixed(1)}Cr`
  if (v >= 1e5) return `${(v / 1e5).toFixed(1)}L`
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}k`
  return `${v}`
}
const rsiTone = (r) => {
  if (r == null) return 'mid'
  if (r > 75) return 'hot'          // overbought
  if (r >= 50 && r <= 65) return 'good' // healthy uptrend zone
  if (r < 40) return 'weak'         // weak / oversold
  return 'mid'
}

// Theme toggle mirrors the main app so the standalone page respects the user's choice.
function useTheme() {
  const [theme, setTheme] = useState(() => { try { return localStorage.getItem('theme') } catch { return null } })
  useEffect(() => {
    if (theme) document.documentElement.setAttribute('data-theme', theme)
    else document.documentElement.removeAttribute('data-theme')
    try { theme ? localStorage.setItem('theme', theme) : localStorage.removeItem('theme') } catch { /* ignore */ }
  }, [theme])
  const isDark = theme ? theme === 'dark' : window.matchMedia?.('(prefers-color-scheme: dark)').matches
  return [isDark, () => setTheme(isDark ? 'light' : 'dark')]
}

const fmtAge = (d) => (d == null ? '' : d < 1 ? 'today' : d < 2 ? '1d ago' : `${Math.round(d)}d ago`)
const fmtCr = (v) => {
  if (v == null) return '—'
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(2)}L Cr`
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(1)}k Cr`
  return `₹${v.toLocaleString('en-IN')} Cr`
}
const growthCls = (v) => (v == null ? '' : v > 0 ? 'up' : v < 0 ? 'down' : '')

// Build a list of plain factual signals from data the screener already has. These are
// observations ("at 52w high", "RSI elevated"), NOT recommendations or entry calls.
function buildSignals(s, news) {
  const sig = []
  if (s.from_52w_high != null) {
    if (s.from_52w_high >= -2) sig.push({ t: 'Trading at / near its 52-week high', tone: 'up' })
    else if (s.from_52w_high <= -25) sig.push({ t: `${Math.abs(s.from_52w_high).toFixed(0)}% below its 52-week high`, tone: 'down' })
  }
  if (s.rsi != null) {
    if (s.rsi > 75) sig.push({ t: `RSI ${s.rsi.toFixed(0)} — overbought zone`, tone: 'warn' })
    else if (s.rsi >= 50 && s.rsi <= 65) sig.push({ t: `RSI ${s.rsi.toFixed(0)} — healthy uptrend zone`, tone: 'up' })
    else if (s.rsi < 40) sig.push({ t: `RSI ${s.rsi.toFixed(0)} — weak / oversold`, tone: 'down' })
    else sig.push({ t: `RSI ${s.rsi.toFixed(0)} — neutral`, tone: '' })
  }
  if (s.rel_strength != null) {
    if (s.rel_strength > 0) sig.push({ t: `Outperforming its sector this week (+${s.rel_strength.toFixed(1)}pp)`, tone: 'up' })
    else if (s.rel_strength < 0) sig.push({ t: `Lagging its sector this week (${s.rel_strength.toFixed(1)}pp)`, tone: 'down' })
  }
  const f = s.fundamentals || {}
  if (f.pat_yoy_pct != null) sig.push({ t: `Latest quarter PAT ${f.pat_yoy_pct > 0 ? '+' : ''}${f.pat_yoy_pct}% YoY`, tone: growthCls(f.pat_yoy_pct) })
  else if (f.pat_yoy_label) sig.push({ t: `Latest quarter: ${f.pat_yoy_label}`, tone: '' })
  // Aggregate unique news catalyst tags into one factual line.
  const cats = [...new Set((news?.data?.headlines || []).flatMap((h) => h.catalysts || []))]
  if (cats.length) sig.push({ t: `Recent news themes: ${cats.join(', ')}`, tone: '' })
  return sig
}

function TechLevels({ s }) {
  const L = s.levels || {}
  const price = s.price
  if (L.recent_high == null) return null
  const rupeeMove = (price != null && L.typical_move_pct != null) ? Math.round(price * L.typical_move_pct / 100) : null
  const pos = L.range_position
  const where = pos == null ? '' : pos >= 70 ? 'near the top of' : pos <= 30 ? 'near the bottom of' : 'in the middle of'
  const trend = (price != null && L.dma20 != null && L.dma50 != null)
    ? (price > L.dma20 && price > L.dma50 ? 'above both averages (uptrend)'
      : price < L.dma20 && price < L.dma50 ? 'below both averages (downtrend)'
      : 'between its averages (mixed)')
    : null
  return (
    <>
      <div className="scr-brief-hd" style={{ marginTop: 16 }}>Technical levels — explained simply</div>
      <ul className="scr-sig">
        <li><span className="dot" />
          <span><b>Recent range (last month):</b> ₹{L.recent_low?.toLocaleString('en-IN')} to ₹{L.recent_high?.toLocaleString('en-IN')}.
          The low is the <b>floor</b> buyers have defended; the high is the <b>ceiling</b> it keeps hitting.
          {pos != null && <> Right now it sits <b>{where}</b> that band ({pos}%).</>}</span>
        </li>
        <li><span className="dot" />
          <span><b>Typical daily move:</b> about <b>{L.typical_move_pct}%</b>
          {rupeeMove != null && <> — roughly ₹{rupeeMove.toLocaleString('en-IN')} up or down on a normal day</>}.
          Bigger number = bumpier ride, so any plan needs more breathing room.</span>
        </li>
        {L.dma20 != null && (
          <li><span className="dot" />
            <span><b>Averages:</b> 20-day ₹{L.dma20?.toLocaleString('en-IN')}{L.dma50 != null && <> · 50-day ₹{L.dma50?.toLocaleString('en-IN')}</>}.
            Price is {trend}. Above the lines = the trend is up; below = down.</span>
          </li>
        )}
      </ul>
      <div className="scr-brief-note">
        How to read it, plainly: prices often <b>bounce up</b> near the recent low and <b>stall</b> near the recent high.
        The 20/50-day averages show which way the tide is flowing. The typical daily move tells you how much wiggle is normal.
        These are just the chart’s facts — <b>what you do with them is your decision</b>, not a suggestion from this tool.
      </div>
    </>
  )
}

function BriefPanel({ s, news }) {
  const f = s.fundamentals || {}
  const signals = buildSignals(s, news)
  return (
    <div className="scr-brief">
      {/* LEFT: factual signals + latest results / fundamentals */}
      <div className="scr-brief-col">
        <div className="scr-brief-hd">What the data shows — facts, you decide</div>
        <ul className="scr-sig">
          {signals.length === 0 ? <li className="scr-brief-none">No standout signals.</li>
            : signals.map((g, i) => <li key={i}><span className={`dot ${g.tone}`} />{g.t}</li>)}
        </ul>

        <div className="scr-brief-hd" style={{ marginTop: 16 }}>
          {f.has_results ? 'Latest results & fundamentals' : 'Fundamentals'}
        </div>
        {f.has_results || f.market_cap_cr ? (
          <div className="scr-fund">
            <div><span className="k">Market cap</span><span className="v">{fmtCr(f.market_cap_cr)}</span></div>
            <div><span className="k">P/E</span><span className="v">{f.pe_label || '—'}</span></div>
            {f.rev_growth_pct != null && <div><span className="k">{f.rev_growth_label}</span><span className={`v ${growthCls(f.rev_growth_pct)}`}>{f.rev_growth_pct > 0 ? '+' : ''}{f.rev_growth_pct}%</span></div>}
            {f.margin_pct != null && <div><span className="k">{f.margin_label}</span><span className="v">{f.margin_pct}%</span></div>}
            {f.pat_yoy_pct != null && <div><span className="k">PAT YoY</span><span className={`v ${growthCls(f.pat_yoy_pct)}`}>{f.pat_yoy_pct > 0 ? '+' : ''}{f.pat_yoy_pct}%</span></div>}
            {f.quality_value != null && <div><span className="k">{f.quality_label}</span><span className="v">{typeof f.quality_value === 'number' ? `${f.quality_value}%` : f.quality_value}</span></div>}
          </div>
        ) : <div className="scr-brief-none">Quarterly KPIs not researched for this name yet.</div>}
        {f.note && <div className="scr-brief-note">{f.note}</div>}

        <TechLevels s={s} />
      </div>

      {/* RIGHT: recent news */}
      <div className="scr-brief-col">
        <div className="scr-brief-hd">Recent news{news?.data?.company ? ` — ${news.data.company}` : ''}</div>
        {!news || news.loading ? <div className="scr-news-empty">Loading news…</div>
          : news.error ? <div className="scr-news-empty">Couldn’t load news right now.</div>
          : (news.data?.headlines || []).length === 0 ? <div className="scr-news-empty">No headlines in the last 2 weeks.</div>
          : news.data.headlines.map((h, i) => (
            <a key={i} className="scr-news-item" href={h.link} target="_blank" rel="noopener noreferrer">
              <div className="scr-news-title">{h.title}</div>
              <div className="scr-news-meta">
                {h.source && <span>{h.source}</span>}
                {h.age_days != null && <span>· {fmtAge(h.age_days)}</span>}
                {(h.catalysts || []).map((c) => <span key={c} className="scr-cat">{c}</span>)}
              </div>
            </a>
          ))}
        <div className="scr-news-disc">Facts for context only — not a verified cause of any move, and not investment advice.</div>
      </div>
    </div>
  )
}

function Row({ s, expanded, news, onToggle }) {
  return (
    <>
      <tr>
        <td className="scr-rank">{s.rank}</td>
        <td className="l">
          <div className="scr-tk">{s.ticker}</div>
          <div className="scr-nm">{s.name}</div>
        </td>
        <td className="l"><span className="scr-sec-pill">{SECTOR_LABELS[s.sector] || s.sector}</span></td>
        <td>₹{s.price?.toLocaleString('en-IN')}</td>
        <td className={pctCls(s.d1)}>{fmtPct(s.d1)}</td>
        <td className={pctCls(s.w1)}>{fmtPct(s.w1)}</td>
        <td className={pctCls(s.m1)}>{fmtPct(s.m1)}</td>
        <td><span className={`scr-rsi ${rsiTone(s.rsi)}`}>{s.rsi == null ? '—' : s.rsi.toFixed(0)}</span></td>
        <td className={pctCls(s.rel_strength)}>{s.rel_strength == null ? '—' : `${s.rel_strength > 0 ? '+' : ''}${s.rel_strength.toFixed(1)}`}</td>
        <td className={pctCls(s.from_52w_high)}>{s.from_52w_high == null ? '—' : `${s.from_52w_high.toFixed(1)}%`}</td>
        <td>{fmtVol(s.volume)}</td>
        <td className="scr-score">{s.score == null ? '—' : s.score.toFixed(1)}</td>
        <td>
          <button className={`scr-newsbtn ${expanded ? 'open' : ''}`} onClick={() => onToggle(s.ticker)}>
            {expanded ? 'Hide' : 'Watch ▾'}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td className="scr-news-cell" colSpan={13}><BriefPanel s={s} news={news} /></td>
        </tr>
      )}
    </>
  )
}

function Table({ stocks, expanded, newsCache, onToggle }) {
  return (
    <div className="scr-tbl-scroll">
      <table className="scr-tbl">
        <thead>
          <tr>
            <th>#</th>
            <th className="l">Stock</th>
            <th className="l">Sector</th>
            <th>Price</th>
            <th>1D</th>
            <th>1W</th>
            <th>1M</th>
            <th>RSI</th>
            <th>Rel Str</th>
            <th>52w High</th>
            <th>Volume</th>
            <th>Score</th>
            <th>Watch</th>
          </tr>
        </thead>
        <tbody>
          {stocks.map((s) => (
            <Row key={s.ticker} s={s} expanded={expanded === s.ticker}
                 news={newsCache[s.ticker]} onToggle={onToggle} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Screener() {
  const [isDark, toggleTheme] = useTheme()
  const { loading, data, error } = useAsync(() => api.screener(), [])
  const [view, setView] = useState('rank')   // 'rank' | 'sector'
  const [limit, setLimit] = useState(20)      // 20 | 50
  const [expanded, setExpanded] = useState(null)      // ticker whose news is open
  const [newsCache, setNewsCache] = useState({})       // { ticker: {loading, data, error} }

  const toggleNews = (ticker) => {
    if (expanded === ticker) { setExpanded(null); return }
    setExpanded(ticker)
    if (!newsCache[ticker]) {
      setNewsCache((c) => ({ ...c, [ticker]: { loading: true } }))
      api.stockNews(ticker)
        .then((d) => setNewsCache((c) => ({ ...c, [ticker]: { data: d } })))
        .catch((e) => setNewsCache((c) => ({ ...c, [ticker]: { error: e.message || true } })))
    }
  }

  return (
    <div className="scr-wrap">
      <div className="scr-head">
        <div>
          <h1 className="scr-title">Swing Screener</h1>
          <p className="scr-sub">
            Momentum · relative strength · RSI(14) · volume across the covered sector universe
            {data?.generated_at && ` · updated ${new Date(data.generated_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}`}
          </p>
        </div>
        <button className="theme-toggle" onClick={toggleTheme} title={isDark ? 'Light mode' : 'Dark mode'}>
          {isDark ? '☀' : '☾'}
        </button>
      </div>

      <div className="scr-disc">
        <b>Screening data only — not investment advice.</b> This page ranks stocks on transparent
        technical metrics so you can research candidates yourself. It makes no buy/sell recommendation
        and sets no price targets. Momentum and RSI are computed from daily closes; relative strength is
        a stock's 1-week move minus its sector average. Always do your own due diligence.
      </div>

      {loading ? <Loading what="screener" /> : error ? <ErrorBox error={error} /> : (() => {
        const stocks = data?.stocks || []
        const sectors = data?.sectors || {}

        const controls = (
          <div className="scr-controls">
            <div>
              <span className="scr-seg-label">View</span>
              <div className="scr-seg">
                <button className={view === 'rank' ? 'on' : ''} onClick={() => setView('rank')}>Rank-wise</button>
                <button className={view === 'sector' ? 'on' : ''} onClick={() => setView('sector')}>Sector-wise</button>
              </div>
            </div>
            <div>
              <span className="scr-seg-label">Show</span>
              <div className="scr-seg">
                <button className={limit === 20 ? 'on' : ''} onClick={() => setLimit(20)}>Top 20</button>
                <button className={limit === 50 ? 'on' : ''} onClick={() => setLimit(50)}>Top 50</button>
              </div>
            </div>
          </div>
        )

        if (view === 'rank') {
          return (
            <>
              {controls}
              <Table stocks={stocks.slice(0, limit)} expanded={expanded}
                     newsCache={newsCache} onToggle={toggleNews} />
            </>
          )
        }

        // Sector-wise: group, order sectors by their avg 1W strength, cap each to the limit.
        const grouped = {}
        for (const s of stocks) (grouped[s.sector] ||= []).push(s)
        const orderedSectors = Object.keys(grouped).sort((a, b) => (sectors[b] ?? -999) - (sectors[a] ?? -999))

        return (
          <>
            {controls}
            {orderedSectors.map((sec) => (
              <div key={sec}>
                <h2 className="scr-sector-h">
                  {SECTOR_LABELS[sec] || sec}
                  <span className="avg">sector avg 1W: {sectors[sec] == null ? '—' : `${sectors[sec] > 0 ? '+' : ''}${sectors[sec].toFixed(1)}%`}</span>
                </h2>
                <Table stocks={grouped[sec].slice(0, limit)} expanded={expanded}
                       newsCache={newsCache} onToggle={toggleNews} />
              </div>
            ))}
          </>
        )
      })()}
    </div>
  )
}
