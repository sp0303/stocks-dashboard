import React, { useRef, useState } from 'react'
import { api } from '../api.js'
import { Loading, ErrorBox, useAsync } from './common.jsx'
import ManagerMetrics from './ManagerMetrics.jsx'
import ManagerHoldings from './ManagerHoldings.jsx'
import ManagerTradeLog from './ManagerTradeLog.jsx'

export default function ManagerView({ managers, manager, setManager, onOpenClient, canSwitch = true }) {
  const [reload, setReload] = useState(0)
  const bump = () => setReload((n) => n + 1)
  const cs = useAsync(() => (manager ? api.clients(manager.id) : Promise.resolve([])), [manager, reload])
  const [form, setForm] = useState({ name: '', client_code: '' })
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(null)
  const [editForm, setEditForm] = useState({})
  const [err, setErr] = useState(null)

  async function addClient(e) {
    e.preventDefault()
    if (!form.name || !manager) return
    setBusy(true)
    try { await api.createClient({ ...form, portfolio_manager_id: manager.id }); setForm({ name: '', client_code: '' }); bump() }
    finally { setBusy(false) }
  }
  function startEdit(c) {
    setEditing(c.id); setEditForm({ name: c.name, client_code: c.client_code || '', email: c.email || '' }); setErr(null)
  }
  async function saveEdit(id) { await api.updateClient(id, editForm); setEditing(null); bump() }
  async function toggleStatus(c) {
    await api.updateClient(c.id, { status: c.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE' }); bump()
  }
  async function del(c) {
    if (!window.confirm(`Delete client "${c.name}"? This also deletes their trades and uploads. Cannot be undone.`)) return
    setErr(null)
    try { await api.deleteClient(c.id); bump() } catch (e) { setErr(e.message) }
  }

  return (
    <div>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div>
          <h1>{manager ? manager.name : 'Manager workspace'}</h1>
          <p className="sub">{manager ? `${manager.firm || ''} — your clients` : 'Choose a manager to view their clients.'}</p>
        </div>
        {canSwitch && (
          <div>
            <label>Acting as manager</label>
            <select value={manager?.id || ''} onChange={(e) => setManager(managers.find((m) => m.id === e.target.value))}>
              {managers.map((m) => <option key={m.id} value={m.id}>{m.name} — {m.firm}</option>)}
            </select>
          </div>
        )}
      </div>

      {manager && (
        <>
          <ManagerUpload managerId={manager.id} onDone={bump} />

          <h2>Book metrics — all clients</h2>
          <ManagerMetrics
            managerId={manager.id}
            reload={reload}
            onOpenClient={onOpenClient}
            onEditClient={startEdit}
            onToggleStatus={toggleStatus}
            onDeleteClient={del}
          />

          {cs.data?.length > 0 && (
            <div style={{ marginTop: 32 }}>
              <ManagerHoldings managerId={manager.id} clients={cs.data} />
            </div>
          )}

          {cs.data?.length > 0 && (
            <div style={{ marginTop: 32 }}>
              <h2>Trade log — all accounts</h2>
              <p className="sub" style={{ margin: '0 0 12px' }}>Every closed trade across your clients — click a Reason cell to add why you bought.</p>
              <ManagerTradeLog managerId={manager.id} reload={reload} />
            </div>
          )}
        </>
      )}

      {err && <div className="err" style={{ marginBottom: 10 }}>⚠ {err}</div>}
      {cs.loading ? <Loading what="clients" /> : cs.error ? <ErrorBox error={cs.error} /> : cs.data.length === 0 ? (
        <div className="empty">No clients yet. Add one below, then upload their tradebook.</div>
      ) : null}

      <h2>Add a client</h2>
      <form className="row" onSubmit={addClient}>
        <input placeholder="Client name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input placeholder="Zerodha code (optional)" value={form.client_code} onChange={(e) => setForm({ ...form, client_code: e.target.value })} />
        <button className="btn" disabled={busy || !form.name || !manager}>Add client</button>
      </form>
    </div>
  )
}

// Upload any tradebook(s) from the book: each file is matched to its client by the account
// code printed in it (or the holder's name) on the server. Nothing is routed by guesswork.
function ManagerUpload({ managerId, onDone }) {
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState([])
  const inputRef = useRef(null)

  async function uploadOne(file) {
    try {
      let r
      try {
        r = await api.uploadManagerTradebook(managerId, file)
      } catch (e) {
        if (e.status !== 409 || !/already uploaded/.test(e.message) || !window.confirm(
          `${file.name} was already uploaded for this client.\n\n` +
          'Upload it again anyway? Trades already stored are skipped; only missing ones are added.'
        )) throw e
        r = await api.uploadManagerTradebook(managerId, file, { force: true })
      }
      const s = r.summary
      const by = r.matched_by === 'account' ? `account ${r.client.client_code}` : `name "${r.file_name_on_tradebook}"`
      return { file: file.name, ok: true,
        text: `→ ${r.client.name} (matched by ${by}): imported ${s.imported}, ${s.duplicates} duplicates skipped, ${s.errors} errors.` }
    } catch (e) {
      return { file: file.name, ok: false, text: e.message }
    }
  }

  async function upload(files) {
    if (!files?.length) return
    setBusy(true); setResults([])
    const out = []
    for (const f of files) { out.push(await uploadOne(f)); setResults([...out]) }
    setBusy(false)
    if (inputRef.current) inputRef.current.value = ''
    if (out.some((x) => x.ok)) onDone()
  }

  return (
    <div className="panel" style={{ padding: 14, margin: '8px 0 24px' }}>
      <div className="row" style={{ alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <strong>Upload tradebooks</strong>
        <span className="sub" style={{ flex: 1, minWidth: 220 }}>
          Drop any client's tradebook here — it goes to the client whose account code (or name) is in the file.
        </span>
        <input ref={inputRef} type="file" accept=".xlsx" multiple disabled={busy}
          aria-label="Upload tradebooks for any client"
          onChange={(e) => upload(Array.from(e.target.files || []))} />
        {busy && <span className="sub">Uploading…</span>}
      </div>
      {results.length > 0 && (
        <ul style={{ margin: '10px 0 0', paddingLeft: 18, fontSize: 13 }}>
          {results.map((r, i) => (
            <li key={i} style={{ color: r.ok ? 'var(--up)' : 'var(--down)' }}>
              <strong>{r.file}</strong> {r.ok ? r.text : `— ${r.text}`}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
