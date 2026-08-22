import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { Loading, ErrorBox, useAsync } from './components/common.jsx'
import SuperAdmin from './components/SuperAdmin.jsx'
import ManagerView from './components/ManagerView.jsx'
import ClientDashboard from './components/ClientDashboard.jsx'

export default function App() {
  const [persona, setPersona] = useState('admin') // 'admin' | 'manager'
  const [manager, setManager] = useState(null)     // selected manager (manager persona)
  const [client, setClient] = useState(null)       // selected client (drilled in)
  const [store, setStore] = useState('')

  const managers = useAsync(() => api.managers(), [])

  useEffect(() => { api.health().then((h) => setStore(h.store)).catch(() => {}) }, [])
  useEffect(() => {
    if (!manager && managers.data && managers.data.length) setManager(managers.data[0])
  }, [managers.data, manager])

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

        {managers.loading ? <Loading what="workspace" /> : managers.error ? <ErrorBox error={managers.error} /> : (
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
