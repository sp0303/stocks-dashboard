import React, { useState, useEffect } from 'react'
import { api } from '../api'
import './PortfolioViewer.css'

export function PortfolioViewer({ clientId }) {
  const [portfolio, setPortfolio] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [lastSync, setLastSync] = useState(null)
  const [tradesExpanded, setTradesExpanded] = useState(false)

  // Load portfolio when component mounts
  useEffect(() => {
    loadPortfolio()
  }, [clientId])

  async function loadPortfolio() {
    try {
      const data = await api.portfolio(clientId)
      setPortfolio(data.data)
      setLastSync(data.data?.synced_at)
    } catch (err) {
      console.log('Portfolio not yet synced')
    }
  }

  async function handleFetchData() {
    setError('')
    setLoading(true)
    try {
      const result = await api.portfolioSync(clientId)
      setPortfolio(result.data)
      setLastSync(result.data.synced_at)
      setError(`✓ ${result.message}`)
      setTimeout(() => setError(''), 3000)
    } catch (err) {
      setError(`❌ ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  if (!portfolio) {
    return (
      <div className="portfolio-viewer">
        <div className="portfolio-header">
          <h2>📊 Portfolio Dashboard</h2>
          <button
            onClick={handleFetchData}
            disabled={loading}
            className="btn-fetch"
          >
            {loading ? '⏳ Fetching...' : '🔄 Fetch Latest Data'}
          </button>
        </div>
        <div className="portfolio-empty">
          <p>No data yet. Click "Fetch Latest Data" to sync your portfolio.</p>
        </div>
      </div>
    )
  }

  const summary = portfolio.summary || {}
  const holdings = portfolio.holdings || []
  const trades = portfolio.trades || []
  const margins = portfolio.margins || {}
  const profile = portfolio.profile || {}

  const formatDate = (isoString) => {
    if (!isoString) return 'Never'
    const date = new Date(isoString)
    return date.toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' })
  }

  const formatMoney = (n) => {
    if (!n) return '₹0'
    return '₹' + n.toLocaleString('en-IN', { maximumFractionDigits: 0 })
  }

  const formatPercent = (n) => {
    if (!n) return '0%'
    return (Math.round(n * 100) / 100).toFixed(2) + '%'
  }

  return (
    <div className="portfolio-viewer">
      <div className="portfolio-header">
        <div>
          <h2>📊 Portfolio Dashboard</h2>
          <p className="user-info">
            {profile.user_name} • {profile.email}
          </p>
        </div>
        <button
          onClick={handleFetchData}
          disabled={loading}
          className="btn-fetch"
        >
          {loading ? '⏳ Fetching...' : '🔄 Fetch Latest Data'}
        </button>
      </div>

      {error && (
        <div
          className={`status-message ${
            error.startsWith('✓') ? 'success' : 'error'
          }`}
        >
          {error}
        </div>
      )}

      {/* Summary Cards */}
      <div className="summary-cards">
        <div className="card">
          <div className="card-label">Portfolio Value</div>
          <div className="card-value">{formatMoney(summary.total_value)}</div>
          <div className="card-meta">
            {summary.total_holdings} holdings
          </div>
        </div>

        <div className="card">
          <div className="card-label">Total P&L</div>
          <div className={`card-value ${summary.total_pnl >= 0 ? 'gain' : 'loss'}`}>
            {formatMoney(summary.total_pnl)}
          </div>
          <div className={`card-meta ${summary.total_pnl >= 0 ? 'gain' : 'loss'}`}>
            {formatPercent(summary.pnl_percent)}
          </div>
        </div>

        <div className="card">
          <div className="card-label">Available Cash</div>
          <div className="card-value">
            {formatMoney(margins?.equity?.available?.cash || 0)}
          </div>
          <div className="card-meta">
            Uninvested • Ready to deploy
          </div>
        </div>

        <div className="card">
          <div className="card-label">Deployed Capital</div>
          <div className="card-value">
            {formatMoney(summary.total_value || 0)}
          </div>
          <div className="card-meta">
            In holdings
          </div>
        </div>

        <div className="card">
          <div className="card-label">Last Synced</div>
          <div className="card-value" style={{ fontSize: '14px' }}>
            {formatDate(lastSync)}
          </div>
          <div className="card-meta">Click to refresh</div>
        </div>
      </div>

      {/* Holdings Table */}
      <div className="holdings-section">
        <h3>💼 Holdings ({holdings.length})</h3>
        {holdings.length === 0 ? (
          <p className="empty-message">No holdings</p>
        ) : (
          <div className="holdings-table-wrapper">
            <table className="holdings-table">
              <thead>
                <tr>
                  <th>Stock</th>
                  <th>Qty</th>
                  <th>Avg Price</th>
                  <th>Current</th>
                  <th>Value</th>
                  <th>P&L</th>
                  <th>P&L %</th>
                </tr>
              </thead>
              <tbody>
                {holdings.map((h, idx) => {
                  const value = h.quantity * h.last_price
                  const pnl = h.pnl || 0
                  const pnlPercent = h.quantity > 0 ? (pnl / (h.average_price * h.quantity)) * 100 : 0

                  return (
                    <tr key={idx} className={pnl >= 0 ? 'gain' : 'loss'}>
                      <td className="stock-name">
                        <strong>{h.tradingsymbol}</strong>
                      </td>
                      <td>{h.quantity}</td>
                      <td>{formatMoney(h.average_price)}</td>
                      <td>{formatMoney(h.last_price)}</td>
                      <td>{formatMoney(value)}</td>
                      <td className={pnl >= 0 ? 'gain' : 'loss'}>
                        {formatMoney(pnl)}
                      </td>
                      <td className={pnl >= 0 ? 'gain' : 'loss'}>
                        {formatPercent(pnlPercent)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Recent Trades (Collapsible) */}
      <div className="trades-section">
        <button
          className="trades-toggle"
          onClick={() => setTradesExpanded(!tradesExpanded)}
          style={{ background: 'none', border: 'none', cursor: 'pointer', width: '100%', textAlign: 'left' }}
        >
          <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '12px' }}>
              {tradesExpanded ? '▼' : '▶'}
            </span>
            📈 Recent Trades ({trades.length})
          </h3>
        </button>
        {tradesExpanded && (
          <>
            {trades.length === 0 ? (
              <p className="empty-message">No trades</p>
            ) : (
              <div className="trades-table-wrapper">
                <table className="trades-table">
                  <thead>
                    <tr>
                      <th>Stock</th>
                      <th>Action</th>
                      <th>Date</th>
                      <th>Qty</th>
                      <th>Price</th>
                      <th>Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.slice(0, 10).map((t, idx) => (
                      <tr key={idx} className={t.action === 'BUY' ? 'buy' : 'sell'}>
                        <td className="stock-name">{t.symbol}</td>
                        <td className={t.action === 'BUY' ? 'buy' : 'sell'}>
                          {t.action}
                        </td>
                        <td>{new Date(t.trade_date).toLocaleDateString('en-IN')}</td>
                        <td>{t.quantity}</td>
                        <td>{formatMoney(t.price)}</td>
                        <td>{formatMoney(t.quantity * t.price)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
