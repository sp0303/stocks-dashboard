import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import { ErrorBox, Loading, useAsync } from '../components/common.jsx'

// Opening Range Breakout — read-only view of the live engine.
//
// The page is built around one question the engine has to answer honestly: is the data
// it is writing good enough to trade on yet? That is why Recording is a first-class
// tab and not a diagnostics footnote — until reconciliation scores five clean sessions,
// the strategy stays off and this page says so plainly.

const REFRESH_MS = 20000

const fmt = (v, d = 2) => (v === null || v === undefined ? '—' : Number(v).toFixed(d))
const pct = (v, d = 1) => (v === null || v === undefined ? '—' : `${Number(v).toFixed(d)}%`)

function Pill({ tone = 'mute', children, title }) {
  const tones = {
    ok: { bg: 'var(--accent-wash)', fg: 'var(--accent-ink)', bd: 'var(--accent)' },
    bad: { bg: 'var(--l1)', fg: 'var(--l4)', bd: 'var(--l3)' },
    warn: { bg: '#f6ecd6', fg: '#8a6608', bd: '#c9a441' },
    mute: { bg: 'var(--surface-2)', fg: 'var(--muted)', bd: 'var(--line-strong)' },
  }
  const t = tones[tone] || tones.mute
  return (
    <span title={title} style={{
      display: 'inline-block', padding: '1px 7px', borderRadius: 3, fontSize: 11,
      fontFamily: 'var(--mono)', background: t.bg, color: t.fg,
      border: `1px solid ${t.bd}`, whiteSpace: 'nowrap',
    }}>{children}</span>
  )
}

function Card({ title, sub, children, right }) {
  return (
    <section style={{
      background: 'var(--card)', border: '1px solid var(--line)', borderRadius: 4,
      padding: '14px 16px', marginBottom: 16, boxShadow: 'var(--shadow)',
    }}>
      {(title || right) && (
        <header style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 10 }}>
          <h2 style={{ margin: 0, fontSize: 14, letterSpacing: '.02em' }}>{title}</h2>
          {sub && <span style={{ fontSize: 12, color: 'var(--muted)' }}>{sub}</span>}
          <span style={{ marginLeft: 'auto' }}>{right}</span>
        </header>
      )}
      {children}
    </section>
  )
}

function Table({ head, children, empty }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
        <thead>
          <tr>{head.map((h) => (
            <th key={h} style={{
              textAlign: 'left', padding: '6px 8px', borderBottom: '1px solid var(--line-strong)',
              color: 'var(--muted)', fontSize: 10.5, letterSpacing: '.08em',
              textTransform: 'uppercase', whiteSpace: 'nowrap',
            }}>{h}</th>
          ))}</tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
      {empty}
    </div>
  )
}

const td = { padding: '6px 8px', borderBottom: '1px solid var(--line)', verticalAlign: 'top' }
const tdNum = { ...td, fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }

// ── engine status ──────────────────────────────────────────────────
function EngineBanner({ s }) {
  if (!s) return null
  const store = s.store || {}
  const eng = s.engine
  const feed = eng?.feed
  const hb = eng?.heartbeat
  const stale = hb?.age_s != null && hb.age_s > 120

  let tone = 'bad'
  let line = 'Engine is not running.'
  let why = s.start_error || (!s.enabled ? 'ORB_ENABLED is false in backend/.env.'
    : !store.connected ? store.error : 'Check the backend logs.')

  if (s.running && s.strategy_enabled) { tone = 'ok'; line = 'Engine running — recording and trading on paper.'; why = null }
  else if (s.running) { tone = 'warn'; line = 'Engine running — recording only.'; why = 'The strategy stays off until reconciliation scores five clean sessions.' }

  return (
    <Card>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
        <Pill tone={tone}>{s.running ? (s.strategy_enabled ? 'LIVE' : 'RECORDING') : 'STOPPED'}</Pill>
        <strong style={{ fontSize: 14 }}>{line}</strong>
        {eng?.is_leader === false && <Pill tone="warn" title="Another process holds the engine lock">not leader</Pill>}
        {feed && <Pill tone={feed.connected ? 'ok' : 'bad'}>feed {feed.connected ? 'connected' : 'down'}</Pill>}
        {feed?.seconds_since_last_tick != null && (
          <Pill tone={feed.seconds_since_last_tick > 90 ? 'bad' : 'ok'}>
            last tick {fmt(feed.seconds_since_last_tick, 0)}s ago
          </Pill>
        )}
        {hb && <Pill tone={stale ? 'bad' : 'mute'}>heartbeat {fmt(hb.age_s, 0)}s</Pill>}
        <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--muted)', fontFamily: 'var(--mono)' }}>
          {s.config_version}
        </span>
      </div>
      {why && <p style={{ margin: '8px 0 0', fontSize: 12.5, color: 'var(--muted)' }}>{why}</p>}
      {eng?.recorder && (
        <div style={{ display: 'flex', gap: 18, marginTop: 10, fontSize: 12, flexWrap: 'wrap' }}>
          <span><b>{eng.recorder.symbols_with_ticks}</b>/{eng.recorder.symbols} symbols ticking</span>
          <span><b>{eng.recorder.ticks?.toLocaleString?.() ?? eng.recorder.ticks}</b> ticks</span>
          <span><b>{eng.recorder.bars_written}</b> bars written</span>
          {eng.open_positions?.length > 0 && <span><b>{eng.open_positions.length}</b> open</span>}
          <span>day <b>{fmt(eng.day_r)}R</b></span>
        </div>
      )}
    </Card>
  )
}

function GettingStarted({ s }) {
  // Shown only while the engine is off — which is the state this page opens in until
  // Segment A has run. Ordering matters: the spike answers questions the backfill
  // assumes, and the recorder must not be switched on before there is a universe.
  const store = s?.store || {}
  const steps = [
    ['Answer the Phase 0 questions', 'python scripts/orb_spike.py', true],
    ['Set MONGODB_URL in backend/.env', null, !store.connected],
    ['Build two years of data', 'python scripts/orb_backfill.py all --years 2',
      !store.sessions_1m],
    ['Set ORB_ENABLED=true and restart', null, !s?.enabled],
    ['Leave ORB_STRATEGY_ENABLED=false until Recording passes', null, true],
  ]
  return (
    <Card title="Getting started" sub="the engine is off">
      <ol style={{ margin: 0, paddingLeft: 20, fontSize: 12.5, lineHeight: 1.9 }}>
        {steps.map(([label, cmd, pending], i) => (
          <li key={i} style={{ color: pending ? 'var(--ink)' : 'var(--faint)' }}>
            {label}
            {cmd && <code style={{
              marginLeft: 8, fontFamily: 'var(--mono)', fontSize: 11.5,
              background: 'var(--surface-2)', border: '1px solid var(--line)',
              borderRadius: 3, padding: '1px 5px',
            }}>{cmd}</code>}
          </li>
        ))}
      </ol>
    </Card>
  )
}

// ── exit test ──────────────────────────────────────────────────────
function ExitTest({ test }) {
  if (!test) return null
  const need = test.sessions_required ?? 5
  const have = test.sessions_passing ?? 0
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{ display: 'flex', gap: 3 }}>
        {Array.from({ length: need }).map((_, i) => (
          <span key={i} style={{
            width: 22, height: 8, borderRadius: 2,
            background: i < have ? 'var(--accent)' : 'var(--line-strong)',
          }} />
        ))}
      </div>
      <span style={{ fontSize: 12, color: 'var(--muted)' }}>
        {have}/{need} clean sessions
        {test.worst_agree_pct != null && ` · worst ${pct(test.worst_agree_pct, 2)}`}
      </span>
      <Pill tone={test.passed ? 'ok' : 'warn'}>{test.passed ? 'passed' : 'not yet'}</Pill>
    </div>
  )
}

// ── live tab ───────────────────────────────────────────────────────
function LiveTab({ date }) {
  const day = useAsync(() => api.orbDay(date), [date])
  if (day.loading) return <Loading what="today's session" />
  if (day.error) return <ErrorBox error={day.error} />
  const d = day.data || {}
  if (d.error) return <Card><p style={{ margin: 0, color: 'var(--muted)' }}>{d.error}</p></Card>

  const cal = d.calendar
  const candidates = d.candidates || []

  return (
    <>
      {cal && !cal.trading && (
        <Card><p style={{ margin: 0 }}>
          <Pill tone="mute">not a trading day</Pill>{' '}
          <span style={{ color: 'var(--muted)', fontSize: 12.5 }}>
            Derived from the data: {cal.with_data}/{cal.symbols} symbols produced real bars.
          </span>
        </p></Card>
      )}
      {cal?.half_day && (
        <Card><p style={{ margin: 0, fontSize: 12.5 }}>
          <Pill tone="warn">half day</Pill>{' '}
          Session ends {Math.floor(cal.session_end / 60)}:{String(cal.session_end % 60).padStart(2, '0')},
          square-off moves to {Math.floor(cal.square_off / 60)}:{String(cal.square_off % 60).padStart(2, '0')}.
        </p></Card>
      )}

      <Card title="Signals" sub={`${(d.signals || []).length} today`}>
        {(d.signals || []).length === 0 ? (
          <p style={{ margin: 0, color: 'var(--muted)', fontSize: 12.5 }}>
            No entries. Every candidate and the rule that stopped it is in the table below.
          </p>
        ) : (
          <Table head={['time', 'symbol', 'side', 'entry', 'stop', 'T1', 'T2', 'qty', 'risk']}>
            {d.signals.map((s) => (
              <tr key={`${s.sym}-${s.minute}`}>
                <td style={tdNum}>{s.time}</td>
                <td style={{ ...td, fontWeight: 600 }}>{s.sym}</td>
                <td style={td}><Pill tone={s.side === 'LONG' ? 'ok' : 'bad'}>{s.side}</Pill></td>
                <td style={tdNum}>{fmt(s.entry)}</td>
                <td style={tdNum}>{fmt(s.stop)}</td>
                <td style={tdNum}>{fmt(s.t1)}</td>
                <td style={tdNum}>{fmt(s.t2)}</td>
                <td style={tdNum}>{s.qty}</td>
                <td style={tdNum}>{fmt(s.risk)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <Card title="Candidates" sub={`${d.passed || 0} of ${d.screened || 0} passed the 09:30 gate`}>
        {candidates.length === 0 ? (
          <p style={{ margin: 0, color: 'var(--muted)', fontSize: 12.5 }}>
            Nothing screened for this date.
          </p>
        ) : (
          <Table head={['symbol', '', 'OR high', 'OR low', 'width', 'RVOL', 'turnover', 'stopped by']}>
            {candidates.map((c) => (
              <CandidateRow key={c.sym} c={c} />
            ))}
          </Table>
        )}
      </Card>
    </>
  )
}

function CandidateRow({ c }) {
  const [open, setOpen] = useState(false)
  const failed = (c.trace || []).find((t) => !t.ok)
  return (
    <>
      <tr onClick={() => setOpen(!open)} style={{ cursor: 'pointer' }}>
        <td style={{ ...td, fontWeight: 600 }}>{c.sym}</td>
        <td style={td}><Pill tone={c.passed ? 'ok' : 'mute'}>{c.passed ? 'passed' : c.failed}</Pill></td>
        <td style={tdNum}>{c.or_high != null ? fmt(c.or_high / 100) : '—'}</td>
        <td style={tdNum}>{c.or_low != null ? fmt(c.or_low / 100) : '—'}</td>
        <td style={tdNum}>{pct(c.or_width_pct, 2)}</td>
        <td style={tdNum}>{c.rvol != null ? `${fmt(c.rvol)}×` : '—'}</td>
        <td style={tdNum}>{c.turnover_cr != null ? `₹${fmt(c.turnover_cr, 1)} cr` : '—'}</td>
        <td style={{ ...td, color: 'var(--muted)' }}>{failed ? failed.note || failed.rule : '—'}</td>
      </tr>
      {open && (
        <tr>
          <td colSpan={8} style={{ ...td, background: 'var(--surface-2)' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(230px,1fr))', gap: 6 }}>
              {(c.trace || []).map((t, i) => (
                <div key={i} style={{ fontSize: 11.5, fontFamily: 'var(--mono)', display: 'flex', gap: 6 }}>
                  <Pill tone={t.ok ? 'ok' : 'bad'}>{t.rule}</Pill>
                  <span style={{ color: 'var(--muted)' }}>
                    {String(t.value)}{t.limit != null && ` / ${t.limit}`}
                  </span>
                </div>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

// ── recording tab ──────────────────────────────────────────────────
function RecordingTab() {
  const health = useAsync(() => api.orbHealth(15), [])
  if (health.loading) return <Loading what="reconciliation history" />
  if (health.error) return <ErrorBox error={health.error} />
  const h = health.data || {}
  if (h.error) return <Card><p style={{ margin: 0, color: 'var(--muted)' }}>{h.error}</p></Card>
  const sessions = (h.sessions || []).filter((s) => s.agree_pct != null)

  return (
    <>
      <Card title="Exit test" sub="the strategy stays off until this passes"
        right={<ExitTest test={h.exit_test} />}>
        <p style={{ margin: 0, fontSize: 12.5, color: 'var(--muted)' }}>
          Every night the bars we built from ticks are compared against Angel's own
          candles, minute by minute, and anything that disagrees is replaced with theirs.
          A dropped connection does not produce missing bars — it produces wrong ones,
          and nothing else would flag them.
        </p>
      </Card>

      <Card title="Reconciliation" sub={`${sessions.length} scored sessions`}>
        {sessions.length === 0 ? (
          <p style={{ margin: 0, color: 'var(--muted)', fontSize: 12.5 }}>
            Nothing reconciled yet. The 15:40 job writes the first entry after a session.
          </p>
        ) : (
          <Table head={['date', 'agreement', 'minutes compared', 'symbols', 'repaired', '']}>
            {sessions.map((s) => (
              <tr key={s.date}>
                <td style={tdNum}>{s.date}</td>
                <td style={tdNum}>
                  <span style={{ color: s.agree_pct >= 99.5 ? 'var(--up)' : 'var(--down)' }}>
                    {pct(s.agree_pct, 3)}
                  </span>
                </td>
                <td style={tdNum}>{s.minutes_compared?.toLocaleString?.()}</td>
                <td style={tdNum}>{s.symbols}</td>
                <td style={tdNum}>{s.repaired_symbols}</td>
                <td style={td}>
                  <Pill tone={s.passes_exit_test ? 'ok' : 'bad'}>
                    {s.passes_exit_test ? 'clean' : 'below 99.5%'}
                  </Pill>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </>
  )
}

// ── journal tab ────────────────────────────────────────────────────
function JournalTab() {
  const j = useAsync(() => api.orbJournal(60), [])
  if (j.loading) return <Loading what="the paper journal" />
  if (j.error) return <ErrorBox error={j.error} />
  const d = j.data || {}
  if (d.error) return <Card><p style={{ margin: 0, color: 'var(--muted)' }}>{d.error}</p></Card>
  const trades = d.trades || []

  return (
    <>
      <Card title="Paper result" sub="no order has been placed — these are the rules' decisions, priced off the tick stream">
        <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap' }}>
          {[['trades', d.count], ['total', d.total_r != null ? `${fmt(d.total_r)}R` : '—'],
            ['win rate', pct(d.win_pct)], ['expectancy', d.expectancy_r != null ? `${fmt(d.expectancy_r, 3)}R` : '—']]
            .map(([k, v]) => (
              <div key={k}>
                <div style={{ fontFamily: 'var(--mono)', fontSize: 20 }}>{v ?? '—'}</div>
                <div style={{ fontSize: 10.5, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>{k}</div>
              </div>
            ))}
        </div>
      </Card>

      <Card title="Trades">
        {trades.length === 0 ? (
          <p style={{ margin: 0, color: 'var(--muted)', fontSize: 12.5 }}>
            No paper trades yet.
          </p>
        ) : (
          <Table head={['date', 'symbol', 'side', 'reason', 'price', 'qty', 'R']}>
            {trades.slice().reverse().map((t, i) => (
              <tr key={i}>
                <td style={tdNum}>{t.date}</td>
                <td style={{ ...td, fontWeight: 600 }}>{t.sym}</td>
                <td style={td}><Pill tone={t.side > 0 ? 'ok' : 'bad'}>{t.side > 0 ? 'LONG' : 'SHORT'}</Pill></td>
                <td style={td}>{t.reason}</td>
                <td style={tdNum}>{fmt((t.price || 0) / 100)}</td>
                <td style={tdNum}>{t.qty}</td>
                <td style={{ ...tdNum, color: t.r >= 0 ? 'var(--up)' : 'var(--down)' }}>{fmt(t.r)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </>
  )
}

// ── page ───────────────────────────────────────────────────────────
export default function Orb() {
  const [tab, setTab] = useState('live')
  const [date, setDate] = useState('')
  const [status, setStatus] = useState(null)
  const [statusErr, setStatusErr] = useState(null)

  useEffect(() => {
    let alive = true
    const load = () => api.orbStatus()
      .then((s) => { if (alive) { setStatus(s); setStatusErr(null) } })
      .catch((e) => { if (alive) setStatusErr(e) })
    load()
    const t = setInterval(load, REFRESH_MS)
    return () => { alive = false; clearInterval(t) }
  }, [])

  const tabs = [['live', 'Live'], ['recording', 'Recording'], ['journal', 'Journal']]

  return (
    <div>
      <div className="topbar">
        <div className="brand">Opening<span>·</span>Range</div>
        <div className="persona">
          {tabs.map(([k, label]) => (
            <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{label}</button>
          ))}
        </div>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 10, alignItems: 'center' }}>
          {tab === 'live' && (
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
              style={{ fontSize: 12, padding: '3px 6px', border: '1px solid var(--line)',
                borderRadius: 3, background: 'var(--surface)', color: 'var(--ink)' }} />
          )}
          <a href="/" style={{ fontSize: 12, color: 'var(--muted)' }}>← dashboard</a>
        </span>
      </div>

      <div className="wrap wrap-wide">
        {statusErr ? <ErrorBox error={statusErr} /> : <EngineBanner s={status} />}
        {status && !status.running && <GettingStarted s={status} />}
        {!status?.running && status?.exit_test && (
          <Card title="Exit test" right={<ExitTest test={status.exit_test} />} />
        )}
        {tab === 'live' && <LiveTab date={date} />}
        {tab === 'recording' && <RecordingTab />}
        {tab === 'journal' && <JournalTab />}
      </div>
    </div>
  )
}
