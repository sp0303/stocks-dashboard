import React from 'react'
import { api, inr, inrFull, pct } from '../api.js'
import { Stat, Loading, ErrorBox, useAsync } from './common.jsx'

export default function StockAnalysis({ client, symbol, onBack }) {
  const s = useAsync(() => api.stock(client.id, symbol), [client.id, symbol])

  return (
    <div>
      <button className="btn ghost" onClick={onBack} style={{ marginBottom: 14 }}>← Back to {client.name}</button>
      {s.loading ? <Loading what={`${symbol} analysis`} /> : s.error ? <ErrorBox error={s.error} /> : (
        <Body d={s.data} symbol={symbol} />
      )}
    </div>
  )
}

// Reuse the existing buy/sell badge colors (already themed + dark-mode aware) for
// sentiment, rather than adding new CSS — same green/red meaning either way.
const SENTIMENT_TONE = { POSITIVE: 'buy', NEGATIVE: 'sell', NEUTRAL: '' }

function News({ symbol }) {
  const n = useAsync(() => api.newsForStock(symbol), [symbol])
  if (n.loading) return <Loading what="news" />
  if (n.error) return <ErrorBox error={n.error} />
  if (!n.data.length) {
    return <div className="empty">No news yet — upload a newspaper PDF to start building this stock's news feed.</div>
  }
  return (
    <div className="panel" style={{ padding: 0 }}>
      {n.data.map((item, i) => (
        <div
          key={item.id}
          style={{
            padding: '14px 16px',
            borderBottom: i < n.data.length - 1 ? '1px solid var(--line)' : 'none',
          }}
        >
          <div className="row" style={{ gap: 8, marginBottom: 6 }}>
            <strong>{item.title}</strong>
          </div>
          {item.summary && <p className="sub" style={{ margin: '0 0 8px' }}>{item.summary}</p>}
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            <span className={`badge ${SENTIMENT_TONE[item.sentiment] || ''}`}>{item.sentiment}</span>
            <span className="badge">{item.event_type}</span>
            <span className="sub" style={{ margin: 0 }}>{item.published_at}</span>
          </div>
          {item.related_articles && item.related_articles.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div className="label" style={{ marginBottom: 4 }}>Related coverage</div>
              {item.related_articles.map((a, j) => (
                <div key={j}>
                  <a href={a.url} target="_blank" rel="noreferrer" style={{ fontSize: 13 }}>
                    {a.title}
                  </a>
                  {a.source && <span className="sub" style={{ margin: '0 0 0 6px' }}>— {a.source}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function Body({ d, symbol }) {
  const held = d.current_quantity > 0
  return (
    <div>
      <div className="row" style={{ gap: 12, alignItems: 'baseline' }}>
        <h1 style={{ margin: 0 }}>{d.symbol}</h1>
        <span className="badge">{d.sector}</span>
        {d.cap && d.cap !== '—' && <span className="badge">{d.cap}</span>}
        <span className="badge">{d.asset_class}</span>
        <span className="sub" style={{ margin: 0, marginLeft: 'auto' }} >
          LTP <strong className="tnum">{d.ltp ?? '—'}</strong>
        </span>
      </div>

      {/* P&L cards */}
      <div className="cards">
        <Stat label={held ? 'Current Value' : 'Currently held'} value={held ? inr(d.market_value) : '—'} sub={held ? `${d.current_quantity} @ avg ${d.avg_cost}` : 'fully exited'} />
        <Stat label="Realized P&L" value={inr(d.realized_pnl)} tone={d.realized_pnl >= 0 ? 'up' : 'down'} />
        <Stat label="Unrealized P&L" value={d.unrealized_pnl === null ? '—' : inr(d.unrealized_pnl)} tone={(d.unrealized_pnl || 0) >= 0 ? 'up' : 'down'} />
        <Stat label="Total P&L" value={inr(d.total_pnl)} tone={d.total_pnl >= 0 ? 'up' : 'down'} />
      </div>

      {/* News */}
      <h2>News</h2>
      <News symbol={symbol} />

      {/* Position strip */}
      <div className="cards">
        <Stat label="Qty held" value={d.current_quantity} sub={held ? `avg cost ${d.avg_cost}` : ''} />
        <Stat label="Total bought" value={inr(d.total_bought_value)} sub={`${d.total_bought_qty} shares`} />
        <Stat label="Total sold" value={inr(d.total_sold_value)} sub={`${d.total_sold_qty} shares`} />
      </div>

      {/* Journey */}
      <h2>Journey</h2>
      <div className="panel" style={{ padding: 16 }}>
        <div className="row" style={{ gap: 28, flexWrap: 'wrap' }}>
          <Milestone label="First bought" date={d.first_buy_date} />
          <span className="sub" style={{ margin: 0 }}>→</span>
          <Milestone label="Last bought" date={d.last_buy_date} />
          <span className="sub" style={{ margin: 0 }}>→</span>
          <Milestone label="Last sold" date={d.last_sell_date || '—'} />
        </div>
      </div>

      {/* Timeline */}
      <h2>Transaction timeline</h2>
      <div className="panel" style={{ padding: 0 }}>
        {d.timeline.map((t, i) => (
          <div key={i} className="row" style={{
            justifyContent: 'space-between', padding: '11px 16px',
            borderBottom: i < d.timeline.length - 1 ? '1px solid var(--line)' : 'none',
          }}>
            <div className="row" style={{ gap: 12 }}>
              <span className={`badge ${t.type}`}>{t.type}</span>
              <span className="mono" style={{ color: 'var(--muted)' }}>{t.date}</span>
            </div>
            <div className="row tnum" style={{ gap: 20 }}>
              <span>{t.quantity} @ {t.price}</span>
              <strong style={{ minWidth: 90, textAlign: 'right' }}>{inrFull(t.value)}</strong>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function Milestone({ label, date }) {
  return (
    <div>
      <div className="label" style={{ marginBottom: 4 }}>{label}</div>
      <div className="mono" style={{ fontWeight: 600 }}>{date || '—'}</div>
    </div>
  )
}
