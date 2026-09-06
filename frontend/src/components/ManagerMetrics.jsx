import React, { useState } from 'react'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine,
} from 'recharts'
import { api, inr, inrFull, pct } from '../api.js'
import { Stat, Loading, ErrorBox, useAsync, PALETTE } from './common.jsx'

export default function ManagerMetrics({ managerId, reload, onOpenClient, onEditClient, onToggleStatus, onDeleteClient }) {
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
                  <td style={{ fontWeight: 600, cursor: 'pointer', color: 'var(--accent-ink)' }} data-client-id={c.id} onClick={() => onOpenClient && onOpenClient(c)}>{c.name}</td>
                  <td className="mono">{c.client_code || '—'}</td>
                  <td className="r tnum">{c.trade_count || 0}</td>
                  <td className="r tnum">{inrFull(c.invested)}</td>
                  <td className="r tnum">{inrFull(c.market_value)}</td>
                  <td><span className="badge" style={c.status !== 'ACTIVE' ? { background: 'var(--surface-2)', color: 'var(--muted)' } : {}}>{c.status}</span></td>
                  <td className="r tnum"><span className={c.unrealized_pnl >= 0 ? 'up' : 'down'}>{inrFull(c.unrealized_pnl)}</span></td>
                  <td style={{ textAlign: 'center', display: 'flex', gap: 12, justifyContent: 'center', alignItems: 'center' }}>
                    {onEditClient && (
                      <button onClick={() => onEditClient(c)} style={{
                        background: 'none', border: 'none', color: 'var(--ink)', cursor: 'pointer', fontSize: 18, padding: '4px',
                        lineHeight: 1
                      }} title="Edit">
                        ✎
                      </button>
                    )}
                    {onDeleteClient && (
                      <button onClick={() => onDeleteClient(c)} style={{
                        background: 'none', border: 'none', color: 'var(--down)', cursor: 'pointer', fontSize: 18, padding: '4px',
                        lineHeight: 1
                      }} title="Delete">
                        🗑
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ManagerPerformance managerId={managerId} reload={reload} />
    </div>
  )
}

const BOOK_BENCHMARK_COLORS = {
  total_value: '#1e40af',
  nifty_50: '#dc2626',
  mid_cap: '#ea580c',
  large_cap: '#8b5cf6',
  small_cap: '#059669',
}
const BOOK_BENCHMARK_LABELS = {
  total_value: 'Whole Book',
  nifty_50: 'Nifty 50',
  mid_cap: 'Nifty Midcap 100',
  large_cap: 'Nifty 100 (Large Cap)',
  small_cap: 'Nifty Smallcap 100',
}

function ManagerPerformance({ managerId, reload }) {
  const [benchmarks, setBenchmarks] = useState({ nifty_50: true, mid_cap: true, large_cap: false, small_cap: false })
  const p = useAsync(() => api.managerPerformance(managerId), [managerId, reload])
  if (p.loading) return <Loading what="book performance" />
  if (p.error) return <ErrorBox error={p.error} />
  const { book, clients } = p.data
  if (!book?.length) return null

  const toggleBenchmark = (key) => setBenchmarks((cur) => ({ ...cur, [key]: !cur[key] }))

  // Same profit/loss framing as the client-level chart: raw value would be dominated by
  // deposit timing across clients (one big new account joining looks like a "gain"), so
  // every line is value-minus-invested — pure book-wide gain/loss vs. each benchmark.
  const bookPnl = book.map((d) => ({
    date: d.date,
    pnl: d.total_value != null && d.invested_value != null ? d.total_value - d.invested_value : null,
    nifty_50_pnl: d.nifty_50_value != null && d.invested_value != null ? d.nifty_50_value - d.invested_value : null,
    mid_cap_pnl: d.mid_cap_value != null && d.invested_value != null ? d.mid_cap_value - d.invested_value : null,
    large_cap_pnl: d.large_cap_value != null && d.invested_value != null ? d.large_cap_value - d.invested_value : null,
    small_cap_pnl: d.small_cap_value != null && d.invested_value != null ? d.small_cap_value - d.invested_value : null,
  }))

  // Individual clients on one chart: capital sizes differ hugely across clients, so
  // absolute ₹ would make a big account's line dwarf everyone else's regardless of who's
  // actually doing better. % return puts every client on the same, fair scale.
  const clientDates = Array.from(new Set(clients.flatMap((c) => c.series.map((r) => r.date)))).sort()
  const clientChartData = clientDates.map((date) => {
    const row = { date }
    for (const c of clients) {
      const hit = c.series.find((r) => r.date === date)
      if (hit) row[c.id] = hit.return_pct
    }
    return row
  })

  return (
    <div style={{ marginTop: 16 }}>
      <div className="panel" style={{ padding: 16, marginBottom: 16 }}>
        <h2 style={{ marginTop: 0 }}>Book performance vs. market</h2>
        <p className="sub">
          The whole book's profit/loss vs. what the same total capital would have made in each index — every
          client's own real, mark-to-market performance summed together.
        </p>
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 10, fontSize: 13 }}>Select benchmarks to compare:</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
            {Object.keys(benchmarks).map((key) => (
              <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 13 }}>
                <input type="checkbox" checked={benchmarks[key]} onChange={() => toggleBenchmark(key)} style={{ cursor: 'pointer' }} />
                <span style={{ color: BOOK_BENCHMARK_COLORS[key], fontWeight: 500 }}>{BOOK_BENCHMARK_LABELS[key]}</span>
              </label>
            ))}
          </div>
        </div>
        <ResponsiveContainer width="100%" height={340}>
          <LineChart data={bookPnl} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--muted)' }} minTickGap={40} />
            <YAxis
              tick={{ fontSize: 11, fill: 'var(--muted)' }}
              label={{ value: 'Profit / Loss (₹)', angle: -90, position: 'insideLeft', offset: 10 }}
              width={85}
              tickFormatter={(v) => (v >= 0 ? inr(v) : `-${inr(-v)}`)}
            />
            <Tooltip
              formatter={(v) => (Number(v) >= 0 ? inr(Number(v)) : `-${inr(-Number(v))}`)}
              contentStyle={{ background: 'var(--surface)', border: '1px solid var(--line)', fontSize: 12 }}
            />
            <ReferenceLine y={0} stroke="var(--muted)" strokeDasharray="2 2" />
            <Line type="monotone" dataKey="pnl" name="Whole Book" stroke={BOOK_BENCHMARK_COLORS.total_value} dot={false} strokeWidth={2.5} connectNulls />
            {benchmarks.nifty_50 && <Line type="monotone" dataKey="nifty_50_pnl" name="Nifty 50" stroke={BOOK_BENCHMARK_COLORS.nifty_50} dot={false} strokeWidth={2} strokeDasharray="4 3" connectNulls />}
            {benchmarks.mid_cap && <Line type="monotone" dataKey="mid_cap_pnl" name="Nifty Midcap 100" stroke={BOOK_BENCHMARK_COLORS.mid_cap} dot={false} strokeWidth={2} connectNulls />}
            {benchmarks.large_cap && <Line type="monotone" dataKey="large_cap_pnl" name="Nifty 100 (Large Cap)" stroke={BOOK_BENCHMARK_COLORS.large_cap} dot={false} strokeWidth={2} strokeDasharray="4 3" connectNulls />}
            {benchmarks.small_cap && <Line type="monotone" dataKey="small_cap_pnl" name="Nifty Smallcap 100" stroke={BOOK_BENCHMARK_COLORS.small_cap} dot={false} strokeWidth={2} connectNulls />}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {clients?.length > 0 && (
        <div className="panel" style={{ padding: 16 }}>
          <h2 style={{ marginTop: 0 }}>Individual client performance</h2>
          <p className="sub">
            Each client's % return over time — normalized, not ₹ value, since clients have deployed very different
            amounts of capital and a raw-value comparison would just reflect account size, not who's performing better.
          </p>
          <ResponsiveContainer width="100%" height={340}>
            <LineChart data={clientChartData} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--muted)' }} minTickGap={40} />
              <YAxis
                tick={{ fontSize: 11, fill: 'var(--muted)' }}
                label={{ value: 'Return (%)', angle: -90, position: 'insideLeft', offset: 10 }}
                width={60}
                tickFormatter={(v) => `${v}%`}
              />
              <Tooltip formatter={(v) => `${Number(v).toFixed(2)}%`} contentStyle={{ background: 'var(--surface)', border: '1px solid var(--line)', fontSize: 12 }} />
              <ReferenceLine y={0} stroke="var(--muted)" strokeDasharray="2 2" />
              {clients.map((c, i) => (
                <Line key={c.id} type="monotone" dataKey={c.id} name={c.name} stroke={PALETTE[i % PALETTE.length]} dot={false} strokeWidth={2} connectNulls />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
