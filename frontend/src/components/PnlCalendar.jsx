import React, { useState, useMemo } from 'react'
import { api, inrCompact, heatColor } from '../api.js'
import { useAsync, ErrorBox, Loading } from './common.jsx'

/**
 * P&L Calendar: daily realized P&L from closed trades, visualized as a month grid
 * with a 9-step diverging colour scale (4 red / flat / 4 green).
 *
 * Props:
 *   clientId: required
 *   onDayClick(date): optional callback when user clicks a day (for Trades filter)
 *   compact: boolean — if true, show mini mode (current month, no month nav)
 */
export default function PnlCalendar({ clientId, onDayClick, compact = false }) {
  const { loading, data, error } = useAsync(() => api.pnlCalendar(clientId), [clientId])
  const [month, setMonth] = useState(new Date())

  if (loading) return <Loading what="P&L calendar" />
  if (error) return <ErrorBox error={error} />
  if (!data?.days || Object.keys(data.days).length === 0) {
    return <div style={{ color: 'var(--muted)', fontSize: '14px' }}>No closed trades yet</div>
  }

  // Compute p90 for the month (used to scale intensity of colours)
  const monthKey = month.toLocaleString('en-CA', { year: 'numeric', month: '2-digit' })
  const monthDays = Object.entries(data.days).filter(([d]) => d.startsWith(monthKey))
  const pnlValues = monthDays.map(([_, v]) => Math.abs(v.pnl)).sort((a, b) => a - b)
  const p90 = pnlValues[Math.floor(pnlValues.length * 0.9)] || 10000

  // Build calendar grid for the month
  const year = month.getFullYear()
  const monthNum = month.getMonth()
  const firstDay = new Date(year, monthNum, 1)
  const lastDay = new Date(year, monthNum + 1, 0)
  const startDow = firstDay.getDay() // 0 = Sun
  const daysInMonth = lastDay.getDate()

  // Days of week headers
  const dow = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

  // Range for month navigation (compact mode uses current data range, full mode shows all)
  const [firstDate, lastDate] = [data.range?.first, data.range?.last]
  const canGoPrev = !compact && firstDate && monthKey > firstDate.substring(0, 7)
  const canGoNext = !compact && lastDate && monthKey < lastDate.substring(0, 7)

  const handlePrevMonth = () => setMonth(new Date(year, monthNum - 1, 1))
  const handleNextMonth = () => setMonth(new Date(year, monthNum + 1, 1))

  const handleDayClick = (date) => {
    if (onDayClick) {
      const isoDate = `${year}-${String(monthNum + 1).padStart(2, '0')}-${String(date).padStart(2, '0')}`
      onDayClick(isoDate)
    }
  }

  return (
    <div style={styles.container}>
      {/* Header with month/summary */}
      <div style={styles.header}>
        <div style={styles.headerLeft}>
          <h3 style={styles.title}>
            {month.toLocaleString('en-US', { month: 'long', year: 'numeric' })}
          </h3>
          {!compact && (
            <div style={styles.summary}>
              <span>Realised <strong style={{ color: 'var(--teal)' }}>₹{(data.summary?.realized || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}</strong></span>
              <span>• {data.summary?.win_days || 0}W / {data.summary?.loss_days || 0}L</span>
            </div>
          )}
        </div>
        {!compact && (
          <div style={styles.nav}>
            <button onClick={handlePrevMonth} disabled={!canGoPrev} style={styles.navBtn}>←</button>
            <button onClick={handleNextMonth} disabled={!canGoNext} style={styles.navBtn}>→</button>
          </div>
        )}
      </div>

      {/* Calendar grid */}
      <div style={styles.grid}>
        {/* Day-of-week headers */}
        {dow.map(d => (
          <div key={d} style={styles.dowCell}>{d}</div>
        ))}

        {/* Empty cells before first day */}
        {Array.from({ length: startDow }).map((_, i) => (
          <div key={`empty-${i}`} style={styles.emptyCell} />
        ))}

        {/* Date cells */}
        {Array.from({ length: daysInMonth }).map((_, i) => {
          const date = i + 1
          const dateStr = `${year}-${String(monthNum + 1).padStart(2, '0')}-${String(date).padStart(2, '0')}`
          const dayData = data.days[dateStr]
          const pnl = dayData?.pnl

          return (
            <div
              key={date}
              style={{
                ...styles.cell,
                background: dayData ? heatColor(pnl, p90) : 'var(--paper)',
                cursor: dayData ? 'pointer' : 'default',
                opacity: dayData ? 1 : 0.5,
              }}
              onClick={() => dayData && handleDayClick(date)}
              title={dayData ? `${dayData.trades} trades • ${inrCompact(pnl)}` : 'No trades'}
            >
              <div style={styles.dateNum}>{date}</div>
              {dayData && <div style={styles.pnlText}>{inrCompact(pnl)}</div>}
            </div>
          )
        })}
      </div>

      {/* Legend */}
      {!compact && (
        <div style={styles.legend}>
          <span>Loss</span>
          <div style={{ ...styles.legendSwatch, background: 'var(--l4)' }} />
          <div style={{ ...styles.legendSwatch, background: 'var(--l3)' }} />
          <div style={{ ...styles.legendSwatch, background: 'var(--l2)' }} />
          <div style={{ ...styles.legendSwatch, background: 'var(--l1)' }} />
          <div style={{ ...styles.legendSwatch, background: 'var(--paper)', border: '1px solid var(--line)' }} />
          <div style={{ ...styles.legendSwatch, background: 'var(--g1)' }} />
          <div style={{ ...styles.legendSwatch, background: 'var(--g2)' }} />
          <div style={{ ...styles.legendSwatch, background: 'var(--g3)' }} />
          <div style={{ ...styles.legendSwatch, background: 'var(--g4)' }} />
          <span>Profit</span>
        </div>
      )}
    </div>
  )
}

const styles = {
  container: {
    background: 'var(--card)',
    border: '1px solid var(--line)',
    borderRadius: '12px',
    padding: '20px 22px',
    boxShadow: 'var(--shadow)',
  },
  header: {
    display: 'flex',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    gap: '12px',
    marginBottom: '16px',
    flexWrap: 'wrap',
  },
  headerLeft: {
    display: 'flex',
    alignItems: 'baseline',
    gap: '16px',
  },
  title: {
    margin: 0,
    fontSize: '18px',
    fontWeight: 600,
    fontFamily: 'Fraunces, Georgia, serif',
  },
  summary: {
    fontSize: '13px',
    color: 'var(--muted)',
    display: 'flex',
    gap: '10px',
  },
  nav: {
    display: 'flex',
    gap: '4px',
  },
  navBtn: {
    background: 'var(--paper)',
    border: '1px solid var(--line)',
    borderRadius: '7px',
    padding: '5px 10px',
    cursor: 'pointer',
    fontSize: '14px',
    fontWeight: 600,
    color: 'var(--ink)',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(7, 1fr)',
    gap: '6px',
    marginBottom: '14px',
  },
  dowCell: {
    fontFamily: 'IBM Plex Mono, monospace',
    fontSize: '10.5px',
    color: 'var(--muted)',
    textAlign: 'center',
    paddingBottom: '2px',
    letterSpacing: '0.08em',
  },
  emptyCell: {
    aspectRatio: '1',
    borderRadius: '7px',
  },
  cell: {
    aspectRatio: '1',
    borderRadius: '7px',
    border: '1px solid var(--line)',
    padding: '6px 7px',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'space-between',
    minHeight: '52px',
    transition: 'opacity 0.15s',
  },
  dateNum: {
    fontFamily: 'IBM Plex Mono, monospace',
    fontSize: '10px',
    color: 'var(--muted)',
  },
  pnlText: {
    fontFamily: 'IBM Plex Mono, monospace',
    fontSize: '11px',
    fontWeight: 500,
    lineHeight: 1.15,
  },
  legend: {
    display: 'flex',
    alignItems: 'center',
    gap: '5px',
    fontSize: '11px',
    color: 'var(--muted)',
    flexWrap: 'wrap',
  },
  legendSwatch: {
    width: '15px',
    height: '15px',
    borderRadius: '4px',
  },
}
