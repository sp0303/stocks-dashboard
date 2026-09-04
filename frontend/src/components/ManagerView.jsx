import React, { useState } from 'react'
import { api } from '../api.js'
import { Loading, ErrorBox, useAsync } from './common.jsx'
import ManagerMetrics from './ManagerMetrics.jsx'

export default function ManagerView({ managers, manager, setManager, onOpenClient }) {
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
        <div>
          <label>Acting as manager</label>
          <select value={manager?.id || ''} onChange={(e) => setManager(managers.find((m) => m.id === e.target.value))}>
            {managers.map((m) => <option key={m.id} value={m.id}>{m.name} — {m.firm}</option>)}
          </select>
        </div>
      </div>

      {manager && (
        <>
          <h2>Book metrics — all clients</h2>
          <ManagerMetrics
            managerId={manager.id}
            reload={reload}
            onOpenClient={onOpenClient}
            onEditClient={startEdit}
            onToggleStatus={toggleStatus}
            onDeleteClient={del}
          />
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
