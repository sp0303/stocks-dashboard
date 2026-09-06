import React, { useState, useEffect } from 'react'
import { api } from '../api'
import './AccountSelector.css'

export function AccountSelector({ clientId, onAccountChange }) {
  const [accounts, setAccounts] = useState([])
  const [activeAccount, setActiveAccount] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    loadAccounts()
  }, [clientId])

  async function loadAccounts() {
    try {
      setLoading(true)
      setError('')
      const data = await api.kiteListAccounts(clientId)
      setAccounts(data.accounts || [])
      const active = data.accounts?.find((a) => a.is_active)
      setActiveAccount(active || null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleSelectAccount(accountId) {
    try {
      setError('')
      await api.kiteSelectAccount(clientId, accountId)
      setActiveAccount(accounts.find((a) => a.id === accountId))
      onAccountChange?.(accountId)
    } catch (err) {
      setError(err.message)
    }
  }

  if (loading) {
    return <div className="account-selector loading">Loading accounts...</div>
  }

  if (accounts.length === 0) {
    return null
  }

  return (
    <div className="account-selector">
      <label>📊 Account:</label>
      <select
        value={activeAccount?.id || ''}
        onChange={(e) => handleSelectAccount(e.target.value)}
        className="account-select"
      >
        {accounts.map((acc) => (
          <option key={acc.id} value={acc.id}>
            {acc.name || acc.owner || `Account ${acc.id.slice(0, 8)}`}
          </option>
        ))}
      </select>
      {error && <div className="error-message">{error}</div>}
    </div>
  )
}
