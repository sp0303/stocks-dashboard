import React, { useState } from 'react'
import { api, setToken, setAuth } from '../api.js'

// Basic password gate (Google auth planned later). Super Admin logs in with a password;
// a manager logs in with email + password and is scoped to their own clients only.
export default function Login({ onLoggedIn }) {
  const [role, setRole] = useState('manager')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  async function submit(e) {
    e.preventDefault()
    setErr(null); setBusy(true)
    try {
      const body = role === 'admin' ? { role, password } : { role, email, password }
      const data = await api.login(body)
      setToken(data.token)
      setAuth({ role: data.role, manager: data.manager || null })
      onLoggedIn({ role: data.role, manager: data.manager || null })
    } catch (e2) {
      setErr(e2.message || 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: 'var(--bg, #f4f4f2)' }}>
      <form onSubmit={submit} style={{
        width: 360, maxWidth: '92vw', background: 'var(--surface, #fff)', padding: 28,
        borderRadius: 14, boxShadow: '0 8px 40px rgba(0,0,0,.08)', display: 'flex', flexDirection: 'column', gap: 14,
      }}>
        <div style={{ fontWeight: 700, fontSize: 20 }}>Portfolio·Intelligence</div>
        <div style={{ color: 'var(--muted, #888)', fontSize: 13, marginTop: -8 }}>Sign in to continue</div>

        <div style={{ display: 'flex', gap: 8 }}>
          <button type="button" className={role === 'manager' ? 'btn' : ''}
            onClick={() => { setRole('manager'); setErr(null) }}
            style={role === 'manager' ? {} : ghost}>Manager</button>
          <button type="button" className={role === 'admin' ? 'btn' : ''}
            onClick={() => { setRole('admin'); setErr(null) }}
            style={role === 'admin' ? {} : ghost}>Super Admin</button>
        </div>

        {role === 'manager' && (
          <input type="email" placeholder="Email" value={email} autoFocus
            onChange={(e) => setEmail(e.target.value)} style={inp} />
        )}
        <input type="password" placeholder="Password" value={password} autoFocus={role === 'admin'}
          onChange={(e) => setPassword(e.target.value)} style={inp} />

        {err && <div className="err" style={{ color: 'var(--down, #c0392b)', fontSize: 13 }}>⚠ {err}</div>}
        <button className="btn" disabled={busy || !password || (role === 'manager' && !email)}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}

const inp = { padding: '10px 12px', borderRadius: 8, border: '1px solid var(--border, #ddd)', fontSize: 14 }
const ghost = { flex: 1, padding: '8px 10px', borderRadius: 8, border: '1px solid var(--border, #ddd)', background: 'transparent', cursor: 'pointer' }
