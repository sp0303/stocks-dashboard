import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { Loading, ErrorBox, useAsync } from './components/common.jsx'
import SuperAdmin from './components/SuperAdmin.jsx'
import ManagerView from './components/ManagerView.jsx'
import ClientDashboard from './components/ClientDashboard.jsx'

function readUrlState() {
  const p = new URLSearchParams(window.location.search)
  return {
    persona: p.get('persona') === 'manager' ? 'manager' : 'admin',
    managerId: p.get('managerId') || null,
    clientId: p.get('clientId') || null,
  }
}

export default function App() {
  const initial = readUrlState()
  const [persona, setPersona] = useState(initial.persona) // 'admin' | 'manager'
  const [manager, setManager] = useState(null)             // selected manager (manager persona)
  const [client, setClient] = useState(null)                // selected client (drilled in)
  const [store, setStore] = useState('')
  const [restoring, setRestoring] = useState(!!(initial.managerId || initial.clientId))

  const managers = useAsync(() => api.managers(), [])

  useEffect(() => { api.health().then((h) => setStore(h.store)).catch(() => {}) }, [])

  // Restore manager/client selection from the URL once managers have loaded. Runs once.
  const restoredRef = React.useRef(false)
  useEffect(() => {
    if (!managers.data || restoredRef.current) return
    restoredRef.current = true
    const { managerId, clientId, persona: p } = readUrlState()
    const m = (managerId && managers.data.find((x) => x.id === managerId)) || managers.data[0] || null
    if (m) setManager(m)
    if (!clientId || !m) { setRestoring(false); return }
    api.clients(p === 'manager' ? m.id : undefined)
      .then((list) => {
        const c = list.find((x) => x.id === clientId)
        if (c) setClient(c)
      })
      .finally(() => setRestoring(false))
  }, [managers.data])

  // Keep the URL in sync so a refresh lands back on the same page.
  useEffect(() => {
    if (restoring) return
    const params = new URLSearchParams()
    params.set('persona', persona)
    if (manager) params.set('managerId', manager.id)
    if (client) params.set('clientId', client.id)
    const qs = params.toString()
    const url = qs ? `${window.location.pathname}?${qs}` : window.location.pathname
    window.history.replaceState(null, '', url)
  }, [persona, manager, client])

  function switchPersona(p) {
    setPersona(p)
    setClient(null)
  }

  return (
    <div>
      <div className="topbar">
        <div className="brand">Portfolio<span>·</span>Intelligence</div>
        <span className="store-pill">store: {store || '…'}</span>
        <div className="persona">
          <button className={persona === 'admin' ? 'on' : ''} onClick={() => switchPersona('admin')}>Super Admin</button>
          <button className={persona === 'manager' ? 'on' : ''} onClick={() => switchPersona('manager')}>Manager</button>
        </div>
      </div>

      <div className="wrap">
        <Breadcrumbs
          persona={persona}
          manager={manager}
          client={client}
          onHome={() => { setClient(null) }}
          onManager={() => setClient(null)}
        />

        {managers.loading || restoring ? <Loading what="workspace" /> : managers.error ? <ErrorBox error={managers.error} /> : (
          client ? (
            <ClientDashboard client={client} />
          ) : persona === 'admin' ? (
            <SuperAdmin onOpenManager={(m) => { setManager(m); setPersona('manager') }} />
          ) : (
            <ManagerView
              managers={managers.data}
              manager={manager}
              setManager={setManager}
              onOpenClient={(c) => setClient(c)}
            />
          )
        )}
      </div>
    </div>
  )
}

function Breadcrumbs({ persona, manager, client, onHome, onManager }) {
  const crumbs = []
  if (persona === 'admin') crumbs.push({ label: 'Platform' })
  else {
    crumbs.push({ label: 'Managers' })
    if (manager) crumbs.push({ label: manager.name, onClick: client ? onManager : null })
    if (client) crumbs.push({ label: client.name })
  }
  return (
    <div className="crumbs">
      {crumbs.map((c, i) => (
        <React.Fragment key={i}>
          {i > 0 && <span className="sep">/</span>}
          {c.onClick ? <a onClick={c.onClick}>{c.label}</a> : <span>{c.label}</span>}
        </React.Fragment>
      ))}
    </div>
  )
}
