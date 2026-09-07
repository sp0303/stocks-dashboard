import React, { useState, useMemo } from 'react'
import { api, inrFull, pctPlain } from '../api.js'
import { Loading, ErrorBox, useAsync, Stat } from './common.jsx'

export default function ManagerHoldings({ managerId, clients = [] }) {
  const [selectedClientIds, setSelectedClientIds] = useState(
    clients.length > 0 ? clients.map(c => c.id) : []
  )
  const [sortColumn, setSortColumn] = useState('holding_pct')
  const [sortDir, setSortDir] = useState('desc')
  const [hoveredRow, setHoveredRow] = useState(null)

  const toggle = (clientId) => {
    setSelectedClientIds(prev =>
      prev.includes(clientId)
        ? prev.filter(id => id !== clientId)
        : [...prev, clientId]
    )
  }

  const toggleAll = () => {
    if (selectedClientIds.length === clients.length) {
      setSelectedClientIds([])
    } else {
      setSelectedClientIds(clients.map(c => c.id))
    }
  }

  const holdings = useAsync(
    () => selectedClientIds.length > 0
      ? api.managerHoldings(managerId, selectedClientIds)
      : Promise.resolve({ holdings: [], totals: { market_value: 0, invested_value: 0, unrealized_pnl: 0 }, client_count: 0 }),
    [managerId, selectedClientIds.join(',')]
  )

  const stats = useMemo(() => {
    if (holdings.data) {
      const t = holdings.data.totals
      return {
        marketValue: t.market_value || 0,
        investedValue: t.invested_value || 0,
        unrealizedPnl: t.unrealized_pnl || 0,
        returnPct: t.invested_value > 0 ? ((t.unrealized_pnl / t.invested_value) * 100) : 0
      }
    }
    return { marketValue: 0, investedValue: 0, unrealizedPnl: 0, returnPct: 0 }
  }, [holdings.data])

  const sortedHoldings = useMemo(() => {
    if (!holdings.data?.holdings) return []
    const sorted = [...holdings.data.holdings]
    sorted.sort((a, b) => {
      let aVal = a[sortColumn]
      let bVal = b[sortColumn]
      if (typeof aVal === 'string') {
        return sortDir === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal)
      }
      return sortDir === 'asc' ? aVal - bVal : bVal - aVal
    })
    return sorted
  }, [holdings.data?.holdings, sortColumn, sortDir])

  const handleSort = (column) => {
    if (sortColumn === column) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortColumn(column)
      setSortDir('desc')
    }
  }

  const SortHeader = ({ column, label }) => (
    <th className="r" style={{ cursor: 'pointer', userSelect: 'none' }} onClick={() => handleSort(column)}>
      {label} {sortColumn === column ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
    </th>
  )

  return (
    <div>
      <h2>Holdings by selected clients</h2>

      <div className="panel" style={{ padding: 16, marginBottom: 16 }}>
        <div style={{ fontWeight: 600, marginBottom: 12, fontSize: 13 }}>Select clients to aggregate</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={selectedClientIds.length === clients.length && clients.length > 0}
              onChange={toggleAll}
              style={{ cursor: 'pointer' }}
            />
            <span style={{ fontWeight: 500, fontSize: 13 }}>
              All ({selectedClientIds.length}/{clients.length})
            </span>
          </label>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10 }}>
          {clients.map(client => (
            <label key={client.id} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', padding: 8, border: '1px solid var(--line)', borderRadius: 4 }}>
              <input
                type="checkbox"
                checked={selectedClientIds.includes(client.id)}
                onChange={() => toggle(client.id)}
                style={{ cursor: 'pointer' }}
              />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, fontWeight: 500 }}>{client.name}</div>
                <div style={{ fontSize: 11, color: 'var(--muted)' }}>{client.client_code || '—'}</div>
              </div>
            </label>
          ))}
        </div>
      </div>

      {selectedClientIds.length > 0 && (
        <>
          <div className="cards">
            <Stat label="Total Market Value" value={inrFull(stats.marketValue)} sub={`${selectedClientIds.length} client(s)`} />
            <Stat label="Total Invested" value={inrFull(stats.investedValue)} />
            <Stat label="Unrealized P&L" value={inrFull(stats.unrealizedPnl)} tone={stats.unrealizedPnl >= 0 ? 'up' : 'down'} />
            <Stat label="Return %" value={`${stats.returnPct > 0 ? '+' : ''}${stats.returnPct.toFixed(2)}%`} tone={stats.returnPct >= 0 ? 'up' : 'down'} />
          </div>

          {holdings.loading ? <Loading what="holdings" /> : holdings.error ? <ErrorBox error={holdings.error} /> : (
            <div className="panel tbl-scroll">
              <table>
                <thead>
                  <tr>
                    <SortHeader column="symbol" label="Symbol" />
                    <SortHeader column="qty" label="Qty" />
                    <SortHeader column="buy_avg" label="Buy Avg" />
                    <SortHeader column="buy_value" label="Buy Value" />
                    <SortHeader column="ltp" label="LTP" />
                    <SortHeader column="present_value" label="Present Value" />
                    <SortHeader column="holding_pct" label="Holding %" />
                    <SortHeader column="pnl" label="P&L" />
                    <SortHeader column="pnl_pct" label="P&L %" />
                    <th style={{ cursor: 'pointer', userSelect: 'none' }}>Clients (hover to see)</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedHoldings?.map((h) => (
                    <tr key={h.symbol} onMouseEnter={() => setHoveredRow(h.symbol)} onMouseLeave={() => setHoveredRow(null)}>
                      <td style={{ fontWeight: 600 }}>{h.symbol}</td>
                      <td className="r tnum">{h.qty.toFixed(0)}</td>
                      <td className="r tnum">₹{h.buy_avg.toFixed(2)}</td>
                      <td className="r tnum">{inrFull(h.buy_value)}</td>
                      <td className="r tnum">₹{h.ltp.toFixed(2)}</td>
                      <td className="r tnum">{inrFull(h.present_value)}</td>
                      <td className="r tnum" style={{ fontWeight: 500 }}>{pctPlain(h.holding_pct)}</td>
                      <td className="r tnum"><span className={h.pnl >= 0 ? 'up' : 'down'}>{inrFull(h.pnl)}</span></td>
                      <td className="r tnum"><span className={h.pnl_pct >= 0 ? 'up' : 'down'}>{pctPlain(h.pnl_pct)}</span></td>
                      <td style={{ fontSize: 12, maxWidth: 200, color: hoveredRow === h.symbol ? 'var(--ink)' : 'transparent', transition: 'color 0.2s' }}>
                        {hoveredRow === h.symbol && h.clients?.map((c, i) => (
                          <div key={i}>
                            {c.name} ({c.qty.toFixed(0)})
                          </div>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {selectedClientIds.length === 0 && <div className="empty">Select at least one client to view holdings.</div>}
    </div>
  )
}
