import React, { useState } from 'react'
import { api } from '../api.js'
import { Stat, Loading, ErrorBox, useAsync } from './common.jsx'
import { CorporateActionsAdmin } from './CorporateActions.jsx'

export default function SuperAdmin({ onOpenManager }) {
  const [reload, setReload] = useState(0)
  const bump = () => setReload((n) => n + 1)
  const ov = useAsync(() => api.overview(), [reload])
  const mg = useAsync(() => api.managers(), [reload])
  const [form, setForm] = useState({ name: '', firm: '', email: '' })
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(null) // manager id being edited
  const [editForm, setEditForm] = useState({})
  const [err, setErr] = useState(null)

  async function addManager(e) {
    e.preventDefault()
    if (!form.name) return
    setBusy(true)
    try { await api.createManager(form); setForm({ name: '', firm: '', email: '' }); bump() }
    finally { setBusy(false) }
  }

  function startEdit(m) {
    setEditing(m.id)
    setEditForm({ name: m.name, firm: m.firm || '', email: m.email || '' })
    setErr(null)
  }
  async function saveEdit(id) {
    await api.updateManager(id, editForm); setEditing(null); bump()
  }
  async function toggleStatus(m) {
    await api.updateManager(m.id, { status: m.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE' }); bump()
  }
  async function del(m) {
    if (!window.confirm(`Delete manager "${m.name}"? This cannot be undone.`)) return
    setErr(null)
    try { await api.deleteManager(m.id); bump() }
    catch (e) { setErr(e.message) }
  }

  return (
    <div>
      <h1>Platform overview</h1>
      <p className="sub">Everything on the platform at a glance.</p>

      {ov.loading ? <Loading what="overview" /> : ov.error ? <ErrorBox error={ov.error} /> : (
        <div className="cards">
          <Stat label="Portfolio Managers" value={ov.data.managers} sub={`${ov.data.active_managers} active`} />
          <Stat label="Clients" value={ov.data.clients} />
          <Stat label="Trades stored" value={ov.data.total_trades.toLocaleString('en-IN')} />
        </div>
      )}

      <h2>Corporate actions data</h2>
      <CorporateActionsAdmin />

      <h2>Portfolio Managers</h2>
      {err && <div className="err" style={{ marginBottom: 10 }}>⚠ {err}</div>}
      {mg.loading ? <Loading what="managers" /> : mg.error ? <ErrorBox error={mg.error} /> : (
        <div className="panel tbl-scroll">
          <table>
            <thead>
              <tr><th>Manager</th><th>Firm</th><th>Email</th><th className="r">Clients</th><th>Status</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {mg.data.map((m) => (
                editing === m.id ? (
                  <tr key={m.id}>
                    <td><input value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} /></td>
                    <td><input value={editForm.firm} onChange={(e) => setEditForm({ ...editForm, firm: e.target.value })} /></td>
                    <td><input value={editForm.email} onChange={(e) => setEditForm({ ...editForm, email: e.target.value })} /></td>
                    <td className="r tnum">{m.client_count}</td>
                    <td><span className="badge">{m.status}</span></td>
                    <td>
                      <div className="row">
                        <button className="btn" style={{ padding: '5px 12px' }} onClick={() => saveEdit(m.id)}>Save</button>
                        <button className="btn ghost" style={{ padding: '5px 12px' }} onClick={() => setEditing(null)}>Cancel</button>
                      </div>
                    </td>
                  </tr>
                ) : (
                  <tr key={m.id}>
                    <td style={{ fontWeight: 600, cursor: 'pointer', color: 'var(--accent-ink)' }} onClick={() => onOpenManager(m)}>{m.name}</td>
                    <td>{m.firm || '—'}</td>
                    <td>{m.email || '—'}</td>
                    <td className="r tnum">{m.client_count}</td>
                    <td><span className="badge" style={m.status !== 'ACTIVE' ? { background: 'var(--surface-2)', color: 'var(--muted)' } : {}}>{m.status}</span></td>
                    <td>
                      <div className="row">
                        <button className="btn ghost" style={{ padding: '5px 10px' }} onClick={() => startEdit(m)}>Edit</button>
                        <button className="btn ghost" style={{ padding: '5px 10px' }} onClick={() => toggleStatus(m)}>{m.status === 'ACTIVE' ? 'Deactivate' : 'Activate'}</button>
                        <button className="btn ghost" style={{ padding: '5px 10px', color: 'var(--down)' }} onClick={() => del(m)}>Delete</button>
                      </div>
                    </td>
                  </tr>
                )
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2>Add a manager</h2>
      <form className="row" onSubmit={addManager}>
        <input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input placeholder="Firm" value={form.firm} onChange={(e) => setForm({ ...form, firm: e.target.value })} />
        <input placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <button className="btn" disabled={busy || !form.name}>Add manager</button>
      </form>
    </div>
  )
}
