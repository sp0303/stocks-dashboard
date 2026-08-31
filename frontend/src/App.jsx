import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { Loading, ErrorBox, useAsync } from './components/common.jsx'
import SuperAdmin from './components/SuperAdmin.jsx'
import ManagerView from './components/ManagerView.jsx'
import ClientDashboard from './components/ClientDashboard.jsx'
import Watchlist from './components/Watchlist.jsx'
import SectorResearch from './components/SectorResearch.jsx'

// Small pill showing the live market-data source. Angel One when connected, otherwise
// the app is running on the Yahoo fallback. Polls every 60s.
function BrokerPill() {
  const [st, setSt] = useState(null)
  useEffect(() => {
    let alive = true
    const load = () => api.angelStatus().then((s) => { if (alive) setSt(s) }).catch(() => {})
    load()
    const t = setInterval(load, 60000)
    return () => { alive = false; clearInterval(t) }
  }, [])

  const connected = st?.authenticated
  const enabled = st?.enabled
  const label = connected ? 'Angel One' : enabled ? 'Angel error' : 'Yahoo (fallback)'
  const title = connected
    ? 'Live quotes & history from Angel One SmartAPI'
    : enabled
      ? `Angel configured but not authenticated${st?.error ? ': ' + st.error : ''} — using Yahoo fallback`
      : 'Angel One not configured — using Yahoo fallback'
  const color = st == null ? 'var(--muted)' : connected ? 'var(--up, #0f7a5a)' : enabled ? 'var(--down, #c0392b)' : 'var(--muted)'

  return (
    <span className="broker-pill" title={title}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12,
        padding: '4px 10px', borderRadius: 999, border: '1px solid var(--line)',
        color: 'var(--muted)', whiteSpace: 'nowrap' }}>
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: color,
        boxShadow: connected ? `0 0 0 3px color-mix(in srgb, ${color} 20%, transparent)` : 'none' }} />
      {st == null ? 'checking…' : label}
    </span>
  )
}

function readUrlState() {
  const p = new URLSearchParams(window.location.search)
  return {
    persona: p.get('persona') === 'manager' ? 'manager' : 'admin',
    managerId: p.get('managerId') || null,
    clientId: p.get('clientId') || null,
  }
}

// 'light' | 'dark' | null (null = follow system prefers-color-scheme)
function readStoredTheme() {
  try { return localStorage.getItem('theme') } catch { return null }
}

function ThemeToggle() {
  const [theme, setTheme] = useState(readStoredTheme)

  useEffect(() => {
    if (theme) document.documentElement.setAttribute('data-theme', theme)
    else document.documentElement.removeAttribute('data-theme')
    try {
      if (theme) localStorage.setItem('theme', theme)
      else localStorage.removeItem('theme')
    } catch { /* private mode etc — theme still applies for this session */ }
  }, [theme])

  const isDark = theme
    ? theme === 'dark'
    : window.matchMedia?.('(prefers-color-scheme: dark)').matches

  return (
    <button
      className="theme-toggle"
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
    >
      {isDark ? '☀' : '☾'}
    </button>
  )
}

export default function App() {
  const initial = readUrlState()
  const [persona, setPersona] = useState(initial.persona) // 'admin' | 'manager'
  const [manager, setManager] = useState(null)             // selected manager (manager persona)
  const [client, setClient] = useState(null)                // selected client (drilled in)
  const [managerPage, setManagerPage] = useState('clients') // 'clients' | 'watchlist' | 'rnd' — manager persona only
  const [restoring, setRestoring] = useState(!!(initial.managerId || initial.clientId))

  const managers = useAsync(() => api.managers(), [])

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
    setManagerPage('clients')
  }

  return (
    <div>
      <div className="topbar">
        <div className="brand">Portfolio<span>·</span>Intelligence</div>
        <div className="persona">
          <button className={persona === 'admin' ? 'on' : ''} onClick={() => switchPersona('admin')}>Super Admin</button>
          <button className={persona === 'manager' ? 'on' : ''} onClick={() => switchPersona('manager')}>Manager</button>
        </div>
        {persona === 'manager' && manager && !client && (
          <div className="persona">
            <button className={managerPage === 'clients' ? 'on' : ''} onClick={() => setManagerPage('clients')}>Overview</button>
            <button className={managerPage === 'watchlist' ? 'on' : ''} onClick={() => setManagerPage('watchlist')}>★ Watchlist</button>
            <button className={managerPage === 'rnd' ? 'on' : ''} onClick={() => setManagerPage('rnd')}>R&amp;D</button>
          </div>
        )}
        <BrokerPill />
        <ThemeToggle />
      </div>

      <div className={`wrap${managerPage === 'rnd' && persona === 'manager' && manager && !client ? ' wrap-wide' : ''}`}>
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
          ) : managerPage === 'watchlist' && manager ? (
            <Watchlist scope="managers" id={manager.id} title="Manager watchlist" />
          ) : managerPage === 'rnd' && manager ? (
            <SectorResearch />
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
