import React, { useState } from 'react'
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
    <div className="pnl-cal">
      {/* Header with month/summary */}
      <div className="pnl-cal-header">
        <div className="pnl-cal-hleft">
          <h3 className="pnl-cal-title">
            {month.toLocaleString('en-US', { month: 'long', year: 'numeric' })}
          </h3>
          {!compact && (
            <div className="pnl-cal-summary">
              <span>Realised <strong style={{ color: 'var(--accent-ink)' }}>₹{(data.summary?.realized || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}</strong></span>
              <span>• {data.summary?.win_days || 0}W / {data.summary?.loss_days || 0}L</span>
            </div>
          )}
        </div>
        {!compact && (
          <div className="pnl-cal-nav">
            <button className="pnl-cal-navbtn" onClick={handlePrevMonth} disabled={!canGoPrev}>←</button>
            <button className="pnl-cal-navbtn" onClick={handleNextMonth} disabled={!canGoNext}>→</button>
          </div>
        )}
      </div>

      {/* Calendar grid */}
      <div className="pnl-cal-grid">
        {/* Day-of-week headers */}
        {dow.map(d => (
          <div key={d} className="pnl-cal-dow">{d}</div>
        ))}

        {/* Empty cells before first day */}
        {Array.from({ length: startDow }).map((_, i) => (
          <div key={`empty-${i}`} className="pnl-cal-empty" />
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
              className="pnl-cal-cell"
              style={{
                background: dayData ? heatColor(pnl, p90) : 'var(--paper)',
                cursor: dayData ? 'pointer' : 'default',
                opacity: dayData ? 1 : 0.5,
              }}
              onClick={() => dayData && handleDayClick(date)}
              title={dayData ? `${dayData.trades} trades • ${inrCompact(pnl)}` : 'No trades'}
            >
              <div className="pnl-cal-date">{date}</div>
              {dayData && <div className="pnl-cal-pnl">{inrCompact(pnl)}</div>}
            </div>
          )
        })}
      </div>

      {/* Legend */}
      {!compact && (
        <div className="pnl-cal-legend">
          <span>Loss</span>
          <div className="pnl-cal-swatch" style={{ background: 'var(--l4)' }} />
          <div className="pnl-cal-swatch" style={{ background: 'var(--l3)' }} />
          <div className="pnl-cal-swatch" style={{ background: 'var(--l2)' }} />
          <div className="pnl-cal-swatch" style={{ background: 'var(--l1)' }} />
          <div className="pnl-cal-swatch" style={{ background: 'var(--paper)', border: '1px solid var(--line)' }} />
          <div className="pnl-cal-swatch" style={{ background: 'var(--g1)' }} />
          <div className="pnl-cal-swatch" style={{ background: 'var(--g2)' }} />
          <div className="pnl-cal-swatch" style={{ background: 'var(--g3)' }} />
          <div className="pnl-cal-swatch" style={{ background: 'var(--g4)' }} />
          <span>Profit</span>
        </div>
      )}
    </div>
  )
}
