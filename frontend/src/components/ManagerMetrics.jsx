import React, { useState } from 'react'
import { api, inr, inrFull, pct } from '../api.js'
import { Stat, Loading, ErrorBox, useAsync } from './common.jsx'

export default function ManagerMetrics({ managerId, reload, onOpenClient, onEditClient, onToggleStatus, onDeleteClient }) {
  const [openMenu, setOpenMenu] = useState(null)
  const m = useAsync(() => api.managerMetrics(managerId), [managerId, reload])
  if (m.loading) return <Loading what="book metrics" />
  if (m.error) return <ErrorBox error={m.error} />
  const d = m.data
  const t = d.totals
  if (!t.clients || t.unique_stocks === 0) {
    return <div className="empty">No client trades yet — upload tradebooks to see book-wide metrics.</div>
  }
  return (
    <div>
      <div className="cards">
        <Stat label="Total P&L (all clients)" value={inr(t.total_pnl)} tone={t.total_pnl >= 0 ? 'up' : 'down'} sub={pct(t.return_pct) + ' return'} />
        <Stat label="Book market value" value={inr(t.market_value)} sub={inrFull(t.market_value)} />
        <Stat label="Total invested" value={inr(t.invested_value)} />
        <Stat label="Realized" value={inr(t.realized_pnl)} tone={t.realized_pnl >= 0 ? 'up' : 'down'} />
        <Stat label="Unrealized" value={inr(t.unrealized_pnl)} tone={t.unrealized_pnl >= 0 ? 'up' : 'down'} />
        <Stat label="Clients / Stocks" value={`${t.clients} / ${t.unique_stocks}`} />
      </div>
      <div className="cards">
        {d.most_invested_stock && <Stat label="Most invested" value={d.most_invested_stock.symbol} sub={inr(d.most_invested_stock.invested_value)} />}
        {d.favourite_stock && <Stat label="Favourite (most traded)" value={d.favourite_stock.symbol} sub={`${d.favourite_stock.trade_count} trades`} />}
        {d.top_holding && <Stat label="Top holding" value={d.top_holding.symbol} sub={inr(d.top_holding.market_value)} />}
        {d.best_performer && <Stat label="Best performer" value={d.best_performer.symbol} tone="up" sub={pct(d.best_performer.pct)} />}
        {d.worst_performer && <Stat label="Worst performer" value={d.worst_performer.symbol} tone="down" sub={pct(d.worst_performer.pct)} />}
      </div>
      {d.by_client?.length > 0 && (
        <div className="panel tbl-scroll" style={{ marginTop: 4 }}>
          <table>
            <thead>
              <tr>
                <th>Client</th>
                <th className="mono" style={{ fontSize: 11 }}>Code</th>
                <th className="r">Trades</th>
                <th className="r">Invested</th>
                <th className="r">Market Value</th>
                <th>Status</th>
                <th className="r">Unrealized P&L</th>
                <th style={{ textAlign: 'center' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {d.by_client.map((c) => (
                <tr key={c.id}>
                  <td style={{ fontWeight: 600, cursor: 'pointer', color: 'var(--accent-ink)' }} data-client-id={c.id}>{c.name}</td>
                  <td className="mono">{c.client_code || '—'}</td>
                  <td className="r tnum">{c.trade_count || 0}</td>
                  <td className="r tnum">{inrFull(c.invested)}</td>
                  <td className="r tnum">{inrFull(c.market_value)}</td>
                  <td><span className="badge" style={c.status !== 'ACTIVE' ? { background: 'var(--surface-2)', color: 'var(--muted)' } : {}}>{c.status}</span></td>
                  <td className="r tnum"><span className={c.unrealized_pnl >= 0 ? 'up' : 'down'}>{inrFull(c.unrealized_pnl)}</span></td>
                  <td style={{ textAlign: 'center', position: 'relative' }}>
                    <button
                      onClick={() => setOpenMenu(openMenu === c.id ? null : c.id)}
                      style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 18, padding: '4px 8px' }}
                      title="Actions"
                    >
                      ⋮
                    </button>
                    {openMenu === c.id && (
                      <div style={{
                        position: 'absolute', top: '100%', right: 0, marginTop: 4, background: 'var(--surface)', border: '1px solid var(--line)',
                        borderRadius: 6, minWidth: 140, zIndex: 100, boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
                      }}>
                        {onOpenClient && (
                          <button onClick={() => { onOpenClient(c); setOpenMenu(null); }} style={{
                            display: 'block', width: '100%', textAlign: 'left', padding: '8px 12px', border: 'none',
                            background: 'none', cursor: 'pointer', fontSize: 13, color: 'var(--accent)', borderBottom: '1px solid var(--line)'
                          }}>
                            📂 Open
                          </button>
                        )}
                        {onEditClient && (
                          <button onClick={() => { onEditClient(c); setOpenMenu(null); }} style={{
                            display: 'block', width: '100%', textAlign: 'left', padding: '8px 12px', border: 'none',
                            background: 'none', cursor: 'pointer', fontSize: 13, color: 'var(--ink)', borderBottom: '1px solid var(--line)'
                          }}>
                            ✏️ Edit
                          </button>
                        )}
                        {onToggleStatus && (
                          <button onClick={() => { onToggleStatus(c); setOpenMenu(null); }} style={{
                            display: 'block', width: '100%', textAlign: 'left', padding: '8px 12px', border: 'none',
                            background: 'none', cursor: 'pointer', fontSize: 13, color: 'var(--ink)', borderBottom: '1px solid var(--line)'
                          }}>
                            {c.status === 'ACTIVE' ? '⊗ Deactivate' : '✓ Activate'}
                          </button>
                        )}
                        {onDeleteClient && (
                          <button onClick={() => { onDeleteClient(c); setOpenMenu(null); }} style={{
                            display: 'block', width: '100%', textAlign: 'left', padding: '8px 12px', border: 'none',
                            background: 'none', cursor: 'pointer', fontSize: 13, color: 'var(--down)'
                          }}>
                            🗑️ Delete
                          </button>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
