import React, { useMemo, useState } from 'react'
import { api, inr, inrFull, pct, pctPlain } from '../api.js'
import { Loading, ErrorBox, useAsync } from './common.jsx'
import './MyBoard.css'

// Watching combines two sources: (1) manual ideas (board items with status=watching),
// (2) auto-populated stocks from selected watchlists. Holding is real tradebook
// positions. Exit is manual plans (dragged from Watching or Holding).

function pnlPct(item) {
  if (item.entry_price == null || item.price == null) return null
  return ((item.price - item.entry_price) / item.entry_price) * 100
}

export default function MyBoard({ managerId }) {
  // Five data sources fire in parallel on mount, none waits on another:
  // 1. clients — for Holding lane client-filtering
  // 2. watchlists — lists available for Watching lane
  // 3. board — manual ideas + exit plans
  // 4. watchlistEntries — auto-populate Watching from selected watchlists
  // 5. holdings — real positions for Holding lane
  // selectedClientIds & selectedWatchlistIds stay null ("all") until user touches a checkbox.

  const clients = useAsync(() => api.clients(managerId), [managerId])
  const [selectedClientIds, setSelectedClientIds] = useState(null)
  const allClients = clients.data || []
  const displaySelectedClients = selectedClientIds ?? allClients.map((c) => c.id)

  const watchlists = useAsync(() => api.watchlistLists('managers', managerId), [managerId])
  const [selectedWatchlistIds, setSelectedWatchlistIds] = useState(null)
  const allWatchlists = watchlists.data || []
  const displaySelectedWatchlists = selectedWatchlistIds ?? allWatchlists.map((w) => w.id)

  const [reload, setReload] = useState(0)
  const board = useAsync(() => api.board(managerId), [managerId, reload])

  // Fetch watchlist entries for selected watchlists
  const watchlistEntries = useAsync(async () => {
    if (displaySelectedWatchlists.length === 0) return []
    const allEntries = await Promise.all(
      displaySelectedWatchlists.map(wlId => api.watchlist('managers', managerId, wlId).catch(() => []))
    )
    return allEntries.flat()
  }, [managerId, displaySelectedWatchlists.join(',')])

  const holdings = useAsync(
    () => (selectedClientIds && selectedClientIds.length === 0
      ? Promise.resolve({ holdings: [] })
      : api.managerHoldings(managerId, selectedClientIds)),
    [managerId, selectedClientIds ? selectedClientIds.join(',') : 'all'],
  )

  const [err, setErr] = useState(null)
  const [adding, setAdding] = useState(false)
  const [dragOverExit, setDragOverExit] = useState(false)
  const [dragOverWatching, setDragOverWatching] = useState(false)

  function refresh() { setReload((n) => n + 1) }
  async function run(fn) {
    setErr(null)
    try { await fn() } catch (e) { setErr(e.message) }
    refresh()
  }

  function toggleClient(id) {
    setSelectedClientIds((cur) => {
      const base = cur ?? allClients.map((c) => c.id)
      return base.includes(id) ? base.filter((x) => x !== id) : [...base, id]
    })
  }
  function toggleAllClients() {
    setSelectedClientIds((cur) => {
      const base = cur ?? allClients.map((c) => c.id)
      return base.length === allClients.length ? [] : allClients.map((c) => c.id)
    })
  }

  function toggleWatchlist(id) {
    setSelectedWatchlistIds((cur) => {
      const base = cur ?? allWatchlists.map((w) => w.id)
      return base.includes(id) ? base.filter((x) => x !== id) : [...base, id]
    })
  }
  function toggleAllWatchlists() {
    setSelectedWatchlistIds((cur) => {
      const base = cur ?? allWatchlists.map((w) => w.id)
      return base.length === allWatchlists.length ? [] : allWatchlists.map((w) => w.id)
    })
  }

  // Combine manual board ideas + watchlist entries for Watching lane.
  // Manual ideas have an id, watchlist entries don't, so tag them with wlId source.
  const manualWatchingItems = (board.data || []).filter((i) => i.status === 'watching')
  const watchlistWatchingItems = (watchlistEntries.data || []).map((e) => ({
    ...e,
    _fromWatchlist: true,
    _wlSource: true,
  }))
  const watchingItems = [...manualWatchingItems, ...watchlistWatchingItems]
  const exitItems = (board.data || []).filter((i) => i.status === 'exit')
  const holdingRows = holdings.data?.holdings || []

  // Drag payload is JSON: {origin: 'watching'|'watching-wl'|'exit'|'holding', ...}
  function onDragStartWatching(e, item) {
    const isWatchlist = item._fromWatchlist
    e.dataTransfer.setData('application/json', JSON.stringify({
      origin: isWatchlist ? 'watching-wl' : 'watching',
      itemId: item.id,
      symbol: item.symbol,
      entryPrice: item.entry_price,
      exitPrice: item.exit_price,
      why: item.why,
    }))
  }
  function onDragStartExit(e, item) {
    e.dataTransfer.setData('application/json', JSON.stringify({ origin: 'exit', itemId: item.id }))
  }
  function onDragStartHolding(e, row) {
    e.dataTransfer.setData('application/json', JSON.stringify({
      origin: 'holding', symbol: row.symbol, buyAvg: row.buy_avg,
    }))
  }

  function readPayload(e) {
    try { return JSON.parse(e.dataTransfer.getData('application/json')) } catch { return null }
  }

  async function onDropExit(e) {
    e.preventDefault()
    setDragOverExit(false)
    const p = readPayload(e)
    if (!p) return
    if (p.origin === 'watching') {
      await run(() => api.boardUpdate(managerId, p.itemId, { status: 'exit' }))
    } else if (p.origin === 'watching-wl') {
      // Watchlist item → Exit: create a new board item with source="watching"
      await run(async () => {
        const items = await api.boardAdd(managerId, {
          symbol: p.symbol,
          entryPrice: p.entryPrice ?? undefined,
          exitPrice: p.exitPrice ?? undefined,
          why: p.why || undefined,
          source: 'watching',
        })
        const created = items[items.length - 1]
        await api.boardUpdate(managerId, created.id, { status: 'exit' })
      })
    } else if (p.origin === 'holding') {
      await run(async () => {
        const items = await api.boardAdd(managerId, {
          symbol: p.symbol, entryPrice: p.buyAvg ?? undefined, source: 'holding',
        })
        const created = items[items.length - 1]
        await api.boardUpdate(managerId, created.id, { status: 'exit' })
      })
    }
  }

  async function onDropWatching(e) {
    e.preventDefault()
    setDragOverWatching(false)
    const p = readPayload(e)
    if (!p || p.origin !== 'exit') return // a real holding never demotes to a typed idea
    await run(() => api.boardUpdate(managerId, p.itemId, { status: 'watching' }))
  }

  if (board.loading || clients.loading || watchlists.loading) return <Loading what="board" />
  if (board.error) return <ErrorBox error={board.error} />
  if (clients.error) return <ErrorBox error={clients.error} />
  if (watchlists.error) return <ErrorBox error={watchlists.error} />

  return (
    <div className="myboard">
      <div className="myboard-head">
        <h2>MyBoard</h2>
        <button className="myboard-add-btn" onClick={() => setAdding(true)}>+ Add idea</button>
      </div>
      {err && <div className="warn-banner">{err}</div>}

      <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap', marginBottom: '16px' }}>
        {/* Holding lane: client filters */}
        <div className="myboard-filterbar">
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--muted)', marginBottom: '8px' }}>Holding — clients</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
            <label className="myboard-client-chip myboard-client-all">
              <input type="checkbox" checked={displaySelectedClients.length === allClients.length && allClients.length > 0} onChange={toggleAllClients} />
              All ({displaySelectedClients.length}/{allClients.length})
            </label>
            {allClients.map((c) => (
              <label key={c.id} className="myboard-client-chip">
                <input type="checkbox" checked={displaySelectedClients.includes(c.id)} onChange={() => toggleClient(c.id)} />
                {c.name}
              </label>
            ))}
          </div>
        </div>

        {/* Watching lane: watchlist filters */}
        <div className="myboard-filterbar">
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--muted)', marginBottom: '8px' }}>Watching — watchlists</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
            <label className="myboard-client-chip myboard-client-all">
              <input type="checkbox" checked={displaySelectedWatchlists.length === allWatchlists.length && allWatchlists.length > 0} onChange={toggleAllWatchlists} />
              All ({displaySelectedWatchlists.length}/{allWatchlists.length})
            </label>
            {allWatchlists.map((w) => (
              <label key={w.id} className="myboard-client-chip">
                <input type="checkbox" checked={displaySelectedWatchlists.includes(w.id)} onChange={() => toggleWatchlist(w.id)} />
                {w.name}
              </label>
            ))}
          </div>
        </div>
      </div>

      {adding && (
        <AddCard
          onCancel={() => setAdding(false)}
          onSave={(vals) => run(async () => {
            await api.boardAdd(managerId, vals)
            setAdding(false)
          })}
        />
      )}

      <div className="myboard-cols">
        <div className="myboard-col">
          <div className="myboard-col-head">
            <span className="myboard-col-title">Watching</span>
            <span className="myboard-col-count">{watchingItems.length}</span>
          </div>
          <div className="myboard-col-hint">Manual ideas + watchlist stocks — drag to Exit to plan a sale</div>
          <div
            className={`myboard-col-body${dragOverWatching ? ' drag-over' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragOverWatching(true) }}
            onDragLeave={() => setDragOverWatching(false)}
            onDrop={onDropWatching}
          >
            {watchingItems.map((item) => {
              if (item._fromWatchlist) {
                // Watchlist entry: read-only, draggable to Exit
                return (
                  <WatchlistCard
                    key={`wl-${item.symbol}`}
                    item={item}
                    onDragStart={(e) => onDragStartWatching(e, item)}
                  />
                )
              }
              // Manual board item: editable, removable
              return (
                <WatchingCard
                  key={item.id}
                  item={item}
                  onDragStart={(e) => onDragStartWatching(e, item)}
                  onEditWhy={(why) => run(() => api.boardUpdate(managerId, item.id, { why }))}
                  onEditPlan={(patch) => run(() => api.boardUpdate(managerId, item.id, patch))}
                  onRemove={() => {
                    if (window.confirm(`Remove ${item.symbol} from Watching?`)) run(() => api.boardRemove(managerId, item.id))
                  }}
                />
              )
            })}
            {watchingItems.length === 0 && <div className="myboard-empty">Nothing here</div>}
          </div>
        </div>

        <div className="myboard-col">
          <div className="myboard-col-head">
            <span className="myboard-col-title">Holding</span>
            <span className="myboard-col-count">{holdingRows.length}</span>
          </div>
          <div className="myboard-col-hint">Real positions from the tradebook — drag one to Exit to plan a sell</div>
          <div className="myboard-col-body">
            {holdings.loading ? <Loading what="holdings" /> : holdings.error ? <ErrorBox error={holdings.error} /> : (
              <>
                {holdingRows.map((row) => (
                  <HoldingCard key={row.symbol} row={row} onDragStart={(e) => onDragStartHolding(e, row)} />
                ))}
                {holdingRows.length === 0 && (
                  <div className="myboard-empty">{displaySelectedClients.length === 0 ? 'Select at least one client' : 'No open positions'}</div>
                )}
              </>
            )}
          </div>
        </div>

        <div className="myboard-col">
          <div className="myboard-col-head">
            <span className="myboard-col-title">Exit</span>
            <span className="myboard-col-count">{exitItems.length}</span>
          </div>
          <div className="myboard-col-hint">Exit plans — a note, not a sale</div>
          <div
            className={`myboard-col-body${dragOverExit ? ' drag-over' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragOverExit(true) }}
            onDragLeave={() => setDragOverExit(false)}
            onDrop={onDropExit}
          >
            {exitItems.map((item) => (
              <ExitCard
                key={item.id}
                item={item}
                onDragStart={(e) => onDragStartExit(e, item)}
                onEditWhy={(why) => run(() => api.boardUpdate(managerId, item.id, { why }))}
                onEditPlan={(patch) => run(() => api.boardUpdate(managerId, item.id, patch))}
                onRemove={() => {
                  if (window.confirm(`Remove ${item.symbol} from Exit?`)) run(() => api.boardRemove(managerId, item.id))
                }}
              />
            ))}
            {exitItems.length === 0 && <div className="myboard-empty">Drop a card here</div>}
          </div>
        </div>
      </div>
    </div>
  )
}

function AddCard({ onSave, onCancel }) {
  const [symbol, setSymbol] = useState('')
  const [entryPrice, setEntryPrice] = useState('')
  const [exitPrice, setExitPrice] = useState('')
  const [why, setWhy] = useState('')
  const [busy, setBusy] = useState(false)

  async function save() {
    if (!symbol.trim()) return
    setBusy(true)
    await onSave({
      symbol: symbol.trim().toUpperCase(),
      entryPrice: entryPrice ? Number(entryPrice) : undefined,
      exitPrice: exitPrice ? Number(exitPrice) : undefined,
      why: why.trim() || undefined,
    })
    setBusy(false)
  }

  return (
    <div className="myboard-addform">
      <input placeholder="Symbol (e.g. TCS)" value={symbol} onChange={(e) => setSymbol(e.target.value)} autoFocus />
      <input placeholder="Entry price" type="number" value={entryPrice} onChange={(e) => setEntryPrice(e.target.value)} />
      <input placeholder="Exit price (target)" type="number" value={exitPrice} onChange={(e) => setExitPrice(e.target.value)} />
      <input placeholder="Why? (thesis)" value={why} onChange={(e) => setWhy(e.target.value)} className="myboard-why-input" />
      <button onClick={save} disabled={busy || !symbol.trim()}>{busy ? 'Adding…' : 'Add'}</button>
      <button onClick={onCancel} className="myboard-cancel">Cancel</button>
    </div>
  )
}

// A real, live position — read-only except for dragging it to Exit.
function HoldingCard({ row, onDragStart }) {
  const [showClients, setShowClients] = useState(false)
  return (
    <div className="myboard-card myboard-card-holding" draggable onDragStart={onDragStart}>
      <div className="myboard-card-top">
        <span className="myboard-symbol">{row.symbol}</span>
        <span className="myboard-price">{row.ltp != null ? inr(row.ltp) : '—'}</span>
      </div>
      <div className={`myboard-pnl ${row.pnl >= 0 ? 'up' : 'down'}`}>{pctPlain(row.pnl_pct)} · {inrFull(row.pnl)}</div>
      <div className="myboard-plan">{row.qty} shares · avg {row.buy_avg != null ? inr(row.buy_avg) : '—'}</div>
      <div className="myboard-holding-clients" onClick={() => setShowClients((s) => !s)}>
        {row.clients?.length || 0} client{row.clients?.length === 1 ? '' : 's'} {showClients ? '▾' : '▸'}
      </div>
      {showClients && (
        <div className="myboard-holding-clientlist">
          {row.clients?.map((c, i) => <div key={i}>{c.name} — {c.qty}</div>)}
        </div>
      )}
      <div className="myboard-drag-hint">drag to Exit to plan a sell</div>
    </div>
  )
}

function WatchingCard({ item, onDragStart, onEditWhy, onEditPlan, onRemove }) {
  return (
    <PlanCard
      item={item} onDragStart={onDragStart} onEditWhy={onEditWhy} onEditPlan={onEditPlan} onRemove={onRemove}
    />
  )
}

function ExitCard({ item, onDragStart, onEditWhy, onEditPlan, onRemove }) {
  return (
    <PlanCard
      item={item} onDragStart={onDragStart} onEditWhy={onEditWhy} onEditPlan={onEditPlan} onRemove={onRemove}
      footer={item.source === 'holding' && (
        <div className="myboard-actual">
          From a real holding{item.exited_price != null && <> · price when flagged {inr(item.exited_price)} on {item.exited_at}</>}
        </div>
      )}
    />
  )
}

function PlanCard({ item, onDragStart, onEditWhy, onEditPlan, onRemove, footer }) {
  const [why, setWhy] = useState(item.why || '')
  const [editingPlan, setEditingPlan] = useState(false)
  const [entryPrice, setEntryPrice] = useState(item.entry_price ?? '')
  const [exitPrice, setExitPrice] = useState(item.exit_price ?? '')
  const pnl = pnlPct(item)

  function saveWhy() { if (why !== (item.why || '')) onEditWhy(why) }
  function savePlan() {
    onEditPlan({
      entryPrice: entryPrice === '' ? undefined : Number(entryPrice),
      exitPrice: exitPrice === '' ? undefined : Number(exitPrice),
    })
    setEditingPlan(false)
  }

  return (
    <div className="myboard-card" draggable onDragStart={onDragStart}>
      <div className="myboard-card-top">
        <span className="myboard-symbol">{item.symbol}</span>
        <span className="myboard-price">{item.price != null ? inr(item.price) : '—'}</span>
        <button className="myboard-remove" title="Remove" onClick={onRemove}>×</button>
      </div>

      {pnl != null && <div className={`myboard-pnl ${pnl >= 0 ? 'up' : 'down'}`}>{pct(pnl)} vs plan</div>}

      {editingPlan ? (
        <div className="myboard-plan-edit">
          <input type="number" placeholder="Entry" value={entryPrice} onChange={(e) => setEntryPrice(e.target.value)} />
          <span>→</span>
          <input type="number" placeholder="Exit" value={exitPrice} onChange={(e) => setExitPrice(e.target.value)} />
          <button onClick={savePlan}>✓</button>
        </div>
      ) : (
        <div className="myboard-plan" onClick={() => setEditingPlan(true)} title="Click to edit">
          Entry {item.entry_price != null ? inr(item.entry_price) : '—'} → Exit {item.exit_price != null ? inr(item.exit_price) : '—'}
        </div>
      )}

      {footer}

      <textarea
        className="myboard-why"
        placeholder="Why? (thesis)"
        value={why}
        onChange={(e) => setWhy(e.target.value)}
        onBlur={saveWhy}
        rows={2}
      />
    </div>
  )
}

// Watchlist entry: read-only card showing stock from a watchlist, draggable to Exit.
function WatchlistCard({ item, onDragStart }) {
  return (
    <div className="myboard-card" draggable onDragStart={onDragStart}>
      <div className="myboard-card-top">
        <span className="myboard-symbol">{item.symbol}</span>
        <span className="myboard-price">{item.price != null ? inr(item.price) : '—'}</span>
      </div>
      <div className="myboard-plan">{inr(item.added_price || '—')} on {item.added_date}</div>
      {item.why && <div className="myboard-why" style={{ marginTop: '6px', cursor: 'default', marginBottom: 0, padding: 0, border: 'none', background: 'transparent', fontSize: '12px', color: 'var(--muted)' }}>{item.why}</div>}
      <div className="myboard-drag-hint">from watchlist • drag to Exit to plan a sale</div>
    </div>
  )
}
