import React from 'react'
import { api, pct } from '../api.js'

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

// Newspaper PDF upload -> portfolio-aware news. Upload returns immediately
// (PENDING); OCR + the rest of the pipeline runs in the background on the server,
// so this polls status every few seconds until DONE/FAILED. Shared by the manager
// view (scope="manager") and the client dashboard (scope="client").
export function NewsUploadBar({ scope, ownerId }) {
  const inputRef = React.useRef()
  const pollRef = React.useRef(null)
  const [msg, setMsg] = React.useState(null)
  const [status, setStatus] = React.useState(null)
  const busy = status === 'PENDING' || status === 'PROCESSING'

  React.useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  function poll(uploadId) {
    pollRef.current = setInterval(async () => {
      try {
        const u = await api.newsPdfUpload(uploadId)
        setStatus(u.status)
        if (u.status === 'DONE' || u.status === 'FAILED') {
          clearInterval(pollRef.current)
          if (u.status === 'DONE') {
            setMsg({
              ok: true,
              text: `Processed ${u.page_count} page${u.page_count === 1 ? '' : 's'} — found ${u.items_created} stor${u.items_created === 1 ? 'y' : 'ies'} across ${u.pages_with_news} page${u.pages_with_news === 1 ? '' : 's'}.`,
            })
          } else {
            setMsg({ ok: false, text: u.error || 'Processing failed.' })
          }
        }
      } catch (e) {
        clearInterval(pollRef.current)
        setStatus(null)
        setMsg({ ok: false, text: e.message })
      }
    }, 4000)
  }

  async function upload(file) {
    if (!file) return
    setMsg(null)
    setStatus('PENDING')
    try {
      const r = await api.uploadNewsPdf(scope, ownerId, file)
      poll(r.upload_id)
    } catch (e) {
      setStatus(null)
      setMsg({ ok: false, text: e.message })
    } finally {
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <div className="panel" style={{ padding: 14, marginTop: 8 }}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div>
          <strong>Upload newspaper PDF</strong>
          <div className="sub" style={{ margin: 0 }}>
            Builds portfolio-aware news for held stocks. OCR runs in the background — this can take a few minutes for a full edition.
          </div>
        </div>
        <div className="row">
          <input ref={inputRef} type="file" accept=".pdf" onChange={(e) => upload(e.target.files[0])} disabled={busy} />
        </div>
      </div>
      {busy && (
        <div className="loading" style={{ padding: '8px 0 0' }}>
          {status === 'PROCESSING' ? 'Reading pages (OCR)…' : 'Queued…'}
        </div>
      )}
      {msg && <div style={{ marginTop: 10 }} className={msg.ok ? '' : 'err'}>{msg.ok ? '✓ ' : ''}{msg.text}</div>}
    </div>
  )
}
