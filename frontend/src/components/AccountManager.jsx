import React, { useState, useEffect } from 'react'
import { api } from '../api'
import './AccountManager.css'

export function AccountManager({ clientId, onAccountAdded }) {
  const [showForm, setShowForm] = useState(false)
  const [accounts, setAccounts] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [authMethod, setAuthMethod] = useState('token') // 'token' or 'credentials'
  const [formData, setFormData] = useState({
    name: '',
    owner: '',
    api_key: '',
    // Token-based auth
    access_token: '',
    // Credentials-based auth (fallback)
    api_secret: '',
    user_id: '',
    password: '',
    totp_secret: '',
  })

  useEffect(() => {
    loadAccounts()
  }, [clientId])

  async function loadAccounts() {
    try {
      const data = await api.kiteListAccounts(clientId)
      setAccounts(data.accounts || [])
    } catch (err) {
      console.error('Error loading accounts:', err)
    }
  }

  async function handleAddAccount(e) {
    e.preventDefault()
    try {
      setError('')
      setLoading(true)

      if (!formData.name.trim()) {
        setError('Account name is required')
        setLoading(false)
        return
      }
      if (!formData.api_key.trim()) {
        setError('API Key is required')
        setLoading(false)
        return
      }

      // Validate based on auth method
      if (authMethod === 'token') {
        if (!formData.access_token.trim()) {
          setError('Access Token is required')
          setLoading(false)
          return
        }
      } else {
        // Credentials method
        if (!formData.api_secret.trim() || !formData.user_id.trim() || !formData.password.trim() || !formData.totp_secret.trim()) {
          setError('All credentials required: API Secret, User ID, Password, TOTP Secret')
          setLoading(false)
          return
        }
      }

      await api.kiteAddAccount(clientId, formData)

      // Reset form and reload accounts
      setFormData({
        name: '',
        owner: '',
        api_key: '',
        access_token: '',
        api_secret: '',
        user_id: '',
        password: '',
        totp_secret: '',
      })
      setAuthMethod('token')
      setShowForm(false)
      await loadAccounts()
      onAccountAdded?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleDeleteAccount(accountId) {
    if (!confirm('Delete this account? This cannot be undone.')) {
      return
    }
    try {
      setError('')
      await api.kiteDeleteAccount(clientId, accountId)
      await loadAccounts()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleSyncAccount(accountId) {
    try {
      setError('')
      setLoading(true)
      const result = await api.kiteSyncAccount(clientId, accountId)
      const msg = result.from_cache
        ? `✓ Synced from cache (${result.message})`
        : `✓ Synced ${result.imported} trades`
      setError(msg)
      await loadAccounts()
      setTimeout(() => setError(''), 3000)
    } catch (err) {
      setError(`Error syncing: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="account-manager">
      <div className="account-manager-header">
        <h3>🔐 Kite Accounts</h3>
        <button
          className="btn-add-account"
          onClick={() => setShowForm(!showForm)}
        >
          {showForm ? '✕ Cancel' : '+ Add Account'}
        </button>
      </div>

      {error && (
        <div className={`error-box ${error.startsWith('✓') ? 'success' : 'error'}`}>
          {error}
        </div>
      )}

      {showForm && (
        <form onSubmit={handleAddAccount} className="account-form">
          <div className="form-group">
            <label>Account Name (Display)</label>
            <input
              type="text"
              placeholder="e.g., Sumanth Trading"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              required
            />
          </div>

          <div className="form-group">
            <label>Owner Name (Optional)</label>
            <input
              type="text"
              placeholder="e.g., Sumanth Billa"
              value={formData.owner}
              onChange={(e) => setFormData({ ...formData, owner: e.target.value })}
            />
          </div>

          <div className="form-section-title">Authentication Method</div>

          <div className="form-group" style={{ display: 'flex', gap: '10px' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <input
                type="radio"
                name="authMethod"
                value="token"
                checked={authMethod === 'token'}
                onChange={() => setAuthMethod('token')}
              />
              🔗 Access Token (Recommended - No CAPTCHA)
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <input
                type="radio"
                name="authMethod"
                value="credentials"
                checked={authMethod === 'credentials'}
                onChange={() => setAuthMethod('credentials')}
              />
              🔑 Full Credentials (Requires CAPTCHA)
            </label>
          </div>

          <div className="form-section-title">Kite API Key</div>

          <div className="form-group">
            <label>API Key</label>
            <input
              type="text"
              placeholder="From Kite Console"
              value={formData.api_key}
              onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
              required
            />
          </div>

          {authMethod === 'token' ? (
            <>
              <div className="form-section-title">🔓 Access Token (from Browser Login)</div>
              <div style={{ padding: '10px', backgroundColor: '#f0f0f0', borderRadius: '4px', marginBottom: '10px', fontSize: '12px' }}>
                📌 Steps: (1) Go to https://kite.zerodha.com (2) Log in manually (3) Open DevTools → Network tab (4) Find any API request (5) Copy Authorization header value (6) Paste below
              </div>
              <div className="form-group">
                <label>Access Token</label>
                <textarea
                  placeholder="Paste access_token from browser Authorization header"
                  value={formData.access_token}
                  onChange={(e) => setFormData({ ...formData, access_token: e.target.value })}
                  style={{ minHeight: '60px', fontFamily: 'monospace', fontSize: '12px' }}
                  required
                />
              </div>
            </>
          ) : (
            <>
              <div className="form-section-title">🔐 Kite Credentials</div>
              <div className="form-group">
                <label>API Secret</label>
                <input
                  type="password"
                  placeholder="From Kite Console"
                  value={formData.api_secret}
                  onChange={(e) => setFormData({ ...formData, api_secret: e.target.value })}
                  required
                />
              </div>

              <div className="form-group">
                <label>User ID</label>
                <input
                  type="text"
                  placeholder="e.g., QPJ806"
                  value={formData.user_id}
                  onChange={(e) => setFormData({ ...formData, user_id: e.target.value })}
                  required
                />
              </div>
            </>
          )}

          <div className="form-group">
            <label>Password</label>
            <input
              type="password"
              placeholder="Kite login password"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              required
            />
          </div>

          <div className="form-group">
            <label>TOTP Secret</label>
            <input
              type="text"
              placeholder="From Kite Security Settings"
              value={formData.totp_secret}
              onChange={(e) => setFormData({ ...formData, totp_secret: e.target.value })}
              required
            />
          </div>

          <button
            type="submit"
            className="btn-submit"
            disabled={loading}
          >
            {loading ? 'Adding...' : 'Add Account'}
          </button>
        </form>
      )}

      {accounts.length > 0 && (
        <div className="accounts-list">
          {accounts.map((account) => (
            <div key={account.id} className={`account-item ${account.is_active ? 'active' : ''}`}>
              <div className="account-info">
                <div className="account-name">
                  {account.user_name || account.owner || account.name || 'Unnamed Account'}
                </div>
                <div className="account-details">
                  {account.email && <span className="detail-email">📧 {account.email}</span>}
                  {account.phone && <span className="detail-phone">📱 {account.phone}</span>}
                  {account.account_type && <span className="detail-type">📊 {account.account_type}</span>}
                </div>
                <div className="account-meta">
                  ID: {account.id.slice(0, 8)}
                  {account.profile_fetched_at && (
                    <> • Profile fetched: {new Date(account.profile_fetched_at).toLocaleDateString()}</>
                  )}
                  {account.synced_at && (
                    <> • Last synced: {new Date(account.synced_at).toLocaleString()}</>
                  )}
                </div>
              </div>
              <div className="account-actions">
                {account.is_active && <span className="badge-active">Active</span>}
                <button
                  className="btn-sync"
                  onClick={() => handleSyncAccount(account.id)}
                  title="Manually sync trades and holdings"
                >
                  🔄 Sync
                </button>
                <button
                  className="btn-delete"
                  onClick={() => handleDeleteAccount(account.id)}
                  title="Delete account"
                >
                  🗑️
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {accounts.length === 0 && !showForm && (
        <div className="empty-state">
          <p>No Kite accounts yet.</p>
          <p className="hint">Click "Add Account" to connect your first account.</p>
        </div>
      )}
    </div>
  )
}
