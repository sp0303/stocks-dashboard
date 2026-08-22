import React from 'react'
import { api, inr, inrFull, pct } from '../api.js'
import { Stat, Loading, ErrorBox, useAsync } from './common.jsx'

export default function ManagerMetrics({ managerId, reload }) {
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
            <thead><tr><th>Client</th><th className="r">Invested</th><th className="r">Market value</th><th className="r">Unrealized P&L</th></tr></thead>
            <tbody>
              {d.by_client.map((c) => (
                <tr key={c.client_id}>
                  <td style={{ fontWeight: 600 }}>{c.name}</td>
                  <td className="r tnum">{inrFull(c.invested)}</td>
                  <td className="r tnum">{inrFull(c.market_value)}</td>
                  <td className="r tnum"><span className={c.unrealized_pnl >= 0 ? 'up' : 'down'}>{inrFull(c.unrealized_pnl)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
