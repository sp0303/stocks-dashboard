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

function Row({ s }) {
  return (
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
    </tr>
  )
}

function Table({ stocks }) {
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
          </tr>
        </thead>
        <tbody>
          {stocks.map((s) => <Row key={s.ticker} s={s} />)}
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
              <Table stocks={stocks.slice(0, limit)} />
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
                <Table stocks={grouped[sec].slice(0, limit)} />
              </div>
            ))}
          </>
        )
      })()}
    </div>
  )
}
