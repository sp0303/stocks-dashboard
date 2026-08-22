import React from 'react'
import { pct } from '../api.js'

export function Stat({ label, value, sub, tone }) {
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className={`value tnum ${tone || ''}`}>{value}</div>
      {sub !== undefined && <div className="label" style={{ marginTop: 6, letterSpacing: 0, textTransform: 'none' }}>{sub}</div>}
    </div>
  )
}

export function PnL({ value }) {
  if (value === null || value === undefined) return <span>—</span>
  return <span className={value >= 0 ? 'up' : 'down'}>{pct(value)}</span>
}

export function Loading({ what = 'data' }) {
  return <div className="loading">Loading {what}…</div>
}

export function ErrorBox({ error }) {
  return <div className="err">⚠ {String(error.message || error)}</div>
}

export function useAsync(fn, deps) {
  const [state, setState] = React.useState({ loading: true, data: null, error: null })
  React.useEffect(() => {
    let alive = true
    setState({ loading: true, data: null, error: null })
    fn()
      .then((data) => alive && setState({ loading: false, data, error: null }))
      .catch((error) => alive && setState({ loading: false, data: null, error }))
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return state
}

// Distinct, colour-blind-friendly palette for allocation charts.
export const PALETTE = [
  '#0f7a5a', '#3a86c8', '#c97b1e', '#8a5cd1', '#c0455a',
  '#2aa198', '#b58900', '#6c8ea0', '#9b5094', '#5a8f4d',
]
