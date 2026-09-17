import React, { useEffect, useState, lazy, Suspense } from 'react'
import { api, getToken, getAuth, logout } from './api.js'
import { Loading, ErrorBox, useAsync } from './components/common.jsx'
import Login from './components/Login.jsx'
// Persona screens load on demand so the initial dashboard chunk stays small.
const SuperAdmin = lazy(() => import('./components/SuperAdmin.jsx'))
const ManagerView = lazy(() => import('./components/ManagerView.jsx'))
const ClientDashboard = lazy(() => import('./components/ClientDashboard.jsx'))
const Watchlist = lazy(() => import('./components/Watchlist.jsx'))
const SectorResearch = lazy(() => import('./components/SectorResearch.jsx'))
const MyBoard = lazy(() => import('./components/MyBoard.jsx'))

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

const MANAGER_PAGES = ['clients', 'watchlist', 'rnd', 'board']

function readUrlState() {
  const p = new URLSearchParams(window.location.search)
  const page = p.get('page')
  return {
    persona: p.get('persona') === 'manager' ? 'manager' : 'admin',
    managerId: p.get('managerId') || null,
    clientId: p.get('clientId') || null,
    page: MANAGER_PAGES.includes(page) ? page : 'board',
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

// Login gate: no valid token → show Login; otherwise the dashboard, scoped to the role.
export default function App() {
  const [auth, setAuthState] = useState(() => (getToken() ? getAuth() : null))
  if (!auth) return <Login onLoggedIn={setAuthState} />
  return <Dashboard auth={auth} />
}

function Dashboard({ auth }) {
  const isAdmin = auth.role === 'admin'
  const initial = readUrlState()
  const [persona, setPersona] = useState(isAdmin ? initial.persona : 'manager') // managers are locked to 'manager'
  const [manager, setManager] = useState(isAdmin ? null : (auth.manager || null))
  const [client, setClient] = useState(null)                // selected client (drilled in)
  const [managerPage, setManagerPage] = useState(initial.page) // 'clients' | 'watchlist' | 'rnd' | 'board' — manager persona only
  const [restoring, setRestoring] = useState(!!(initial.managerId || initial.clientId))

  // Managers list is refetched on demand (mgReload) — a manager created in the Super Admin
  // tab must appear in the Manager tab's dropdown, else selection/add-client breaks.
  const [mgReload, setMgReload] = useState(0)
  const refreshManagers = () => setMgReload((n) => n + 1)
  // Admin lists all managers; a manager only ever sees (and is scoped to) themselves.
  const managers = useAsync(
    () => (isAdmin ? api.managers() : Promise.resolve([auth.manager].filter(Boolean))),
    [mgReload])

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
    if (!client && managerPage !== 'clients') params.set('page', managerPage)
    const qs = params.toString()
    const url = qs ? `${window.location.pathname}?${qs}` : window.location.pathname
    window.history.replaceState(null, '', url)
  }, [persona, manager, client, managerPage])

  function switchPersona(p) {
    setPersona(p)
    setClient(null)
    setManagerPage('clients')
    if (p === 'manager') refreshManagers()   // pick up managers just created in Super Admin
  }

  return (
    <div>
      <div className="topbar">
        <div className="brand">Portfolio<span>·</span>Intelligence</div>
        {isAdmin && (
          <div className="persona">
            <button className={persona === 'admin' ? 'on' : ''} onClick={() => switchPersona('admin')}>Super Admin</button>
            <button className={persona === 'manager' ? 'on' : ''} onClick={() => switchPersona('manager')}>Manager</button>
          </div>
        )}
        {persona === 'manager' && manager && !client && (
          <div className="persona">
            <button className={managerPage === 'clients' ? 'on' : ''} onClick={() => setManagerPage('clients')}>Overview</button>
            <button className={managerPage === 'watchlist' ? 'on' : ''} onClick={() => setManagerPage('watchlist')}>★ Watchlist</button>
            <button className={managerPage === 'rnd' ? 'on' : ''} onClick={() => setManagerPage('rnd')}>R&amp;D</button>
            <button className={managerPage === 'board' ? 'on' : ''} onClick={() => setManagerPage('board')}>MyBoard</button>
          </div>
        )}
        <BrokerPill />
        <span style={{ fontSize: 12, color: 'var(--muted)', marginLeft: 8 }}>
          {isAdmin ? 'Super Admin' : (auth.manager?.name || 'Manager')}
        </span>
        <button onClick={logout} title="Sign out" style={{
          background: 'none', border: '1px solid var(--border, #ddd)', borderRadius: 8,
          padding: '4px 10px', cursor: 'pointer', fontSize: 12, marginLeft: 8,
        }}>Sign out</button>
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
          <Suspense fallback={<Loading what="page" />}>
            {client ? (
              <ClientDashboard client={client} />
            ) : persona === 'admin' ? (
              <SuperAdmin onOpenManager={(m) => { setManager(m); setPersona('manager'); refreshManagers() }} />
            ) : managerPage === 'watchlist' && manager ? (
              <Watchlist scope="managers" id={manager.id} title="Manager watchlist" />
            ) : managerPage === 'rnd' && manager ? (
              <SectorResearch />
            ) : managerPage === 'board' && manager ? (
              <MyBoard managerId={manager.id} />
            ) : (
              <ManagerView
                managers={managers.data}
                manager={manager}
                setManager={setManager}
                canSwitch={isAdmin}
                onOpenClient={(c) => setClient(c)}
              />
            )}
          </Suspense>
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
