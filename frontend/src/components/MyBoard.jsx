import React, { useEffect, useState } from 'react'
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
  const [drag, setDrag] = useState(null) // { key, column } — active within-column reorder

  // Notion-style ordering + colors persist per-manager in localStorage. Cards come from
  // mixed sources (real holdings, watchlist entries, manual board items) that don't all
  // have a backend id, so a symbol/id key list per column is the simplest uniform store.
  const orderKey = (col) => `myboard-order-${col}-${managerId}`
  const colorsKey = `myboard-colors-${managerId}`
  const [orders, setOrders] = useState({})   // { watching: [key,…], holding: […], exit: […] }
  const [colors, setColors] = useState({})   // { cardKey: cssColor }

  useEffect(() => {
    const load = (k) => { try { return JSON.parse(localStorage.getItem(k)) } catch { return null } }
    setOrders({
      watching: load(orderKey('watching')) || [],
      holding: load(orderKey('holding')) || [],
      exit: load(orderKey('exit')) || [],
    })
    setColors(load(colorsKey) || {})
  }, [managerId])

  function keyOf(col, item) {
    if (col === 'holding') return `h:${item.symbol}`
    if (item._fromWatchlist) return `wl:${item.symbol}`
    return `b:${item.id}`
  }

  function applyOrder(list, col) {
    const ord = orders[col] || []
    return [...list].sort((a, b) => {
      const ia = ord.indexOf(keyOf(col, a)), ib = ord.indexOf(keyOf(col, b))
      if (ia === -1 && ib === -1) return 0
      if (ia === -1) return 1
      if (ib === -1) return -1
      return ia - ib
    })
  }

  // Full insert reorder (not a swap): pull the dragged key out and splice it in
  // before/after the drop target, then persist the whole column order.
  function reorder(col, displayList, dragKey, targetKey, before) {
    if (dragKey === targetKey) return
    const keys = displayList.map((x) => keyOf(col, x))
    const from = keys.indexOf(dragKey)
    if (from === -1) return
    keys.splice(from, 1)
    let to = keys.indexOf(targetKey)
    if (to === -1) to = keys.length
    else if (!before) to += 1
    keys.splice(to, 0, dragKey)
    setOrders((o) => ({ ...o, [col]: keys }))
    setDrag(null)
    try { localStorage.setItem(orderKey(col), JSON.stringify(keys)) } catch { /* private mode */ }
  }

  function setColor(cardKey, color) {
    setColors((c) => {
      const next = { ...c }
      if (color) next[cardKey] = color; else delete next[cardKey]
      try { localStorage.setItem(colorsKey, JSON.stringify(next)) } catch { /* private mode */ }
      return next
    })
  }

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

  // Combine manual board ideas + watchlist entries for Watching lane, then apply the
  // saved custom order. Manual ideas have an id, watchlist entries don't.
  const manualWatchingItems = (board.data || []).filter((i) => i.status === 'watching')
  const watchlistWatchingItems = (watchlistEntries.data || []).map((e) => ({
    ...e,
    _fromWatchlist: true,
    _wlSource: true,
  }))
  const watchingItems = applyOrder([...manualWatchingItems, ...watchlistWatchingItems], 'watching')
  const exitItems = applyOrder((board.data || []).filter((i) => i.status === 'exit'), 'exit')
  const holdingRows = applyOrder(holdings.data?.holdings || [], 'holding')

  // Drag payload is JSON: {origin: 'watching'|'watching-wl'|'exit'|'holding', ...}.
  // `drag` state carries the within-column reorder key so slots know what is moving.
  function onDragStartWatching(e, item) {
    const isWatchlist = item._fromWatchlist
    setDrag({ key: keyOf('watching', item), column: 'watching' })
    e.dataTransfer.setData('application/json', JSON.stringify({
      origin: isWatchlist ? 'watching-wl' : 'watching',
      itemId: item.id,
      symbol: item.symbol,
      entryPrice: item.entry_price,
      exitPrice: item.exit_price,
      why: item.why,
    }))
    e.dataTransfer.effectAllowed = 'move'
  }
  function onDragStartExit(e, item) {
    setDrag({ key: keyOf('exit', item), column: 'exit' })
    e.dataTransfer.setData('application/json', JSON.stringify({ origin: 'exit', itemId: item.id }))
  }
  function onDragStartHolding(e, row) {
    setDrag({ key: keyOf('holding', row), column: 'holding' })
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
    setDrag(null)
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
    if (!p) return
    if (p.origin === 'exit') {
      // Move from Exit back to Watching
      await run(() => api.boardUpdate(managerId, p.itemId, { status: 'watching' }))
    }
    setDrag(null)
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
              const k = keyOf('watching', item)
              const slot = { column: 'watching', itemKey: k, drag,
                onReorder: (from, to, before) => reorder('watching', watchingItems, from, to, before) }
              if (item._fromWatchlist) {
                return (
                  <ReorderSlot key={`wl-${item.symbol}`} {...slot}>
                    <WatchlistCard
                      item={item}
                      color={colors[k]} onColor={(c) => setColor(k, c)}
                      onDragStart={(e) => onDragStartWatching(e, item)}
                      onAddNotes={(symbol, notes) => run(async () => {
                        await api.boardAdd(managerId, { symbol, why: notes, source: 'watchlist' })
                      })}
                    />
                  </ReorderSlot>
                )
              }
              return (
                <ReorderSlot key={item.id} {...slot}>
                  <WatchingCard
                    item={item}
                    color={colors[k]} onColor={(c) => setColor(k, c)}
                    onDragStart={(e) => onDragStartWatching(e, item)}
                    onEditWhy={(why) => run(() => api.boardUpdate(managerId, item.id, { why }))}
                    onEditPlan={(patch) => run(() => api.boardUpdate(managerId, item.id, patch))}
                    onRemove={() => {
                      if (window.confirm(`Remove ${item.symbol} from Watching?`)) run(() => api.boardRemove(managerId, item.id))
                    }}
                  />
                </ReorderSlot>
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
                {holdingRows.map((row) => {
                  const k = keyOf('holding', row)
                  return (
                    <ReorderSlot key={row.symbol} column="holding" itemKey={k} drag={drag}
                      onReorder={(from, to, before) => reorder('holding', holdingRows, from, to, before)}>
                      <HoldingCard row={row}
                        color={colors[k]} onColor={(c) => setColor(k, c)}
                        onDragStart={(e) => onDragStartHolding(e, row)} onAddNotes={(symbol, notes) => run(async () => {
                        await api.boardAdd(managerId, { symbol, why: notes, source: 'holding' })
                      })} />
                    </ReorderSlot>
                  )
                })}
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
            {exitItems.map((item) => {
              const k = keyOf('exit', item)
              return (
                <ReorderSlot key={item.id} column="exit" itemKey={k} drag={drag}
                  onReorder={(from, to, before) => reorder('exit', exitItems, from, to, before)}>
                  <ExitCard
                    item={item}
                    color={colors[k]} onColor={(c) => setColor(k, c)}
                    onDragStart={(e) => onDragStartExit(e, item)}
                    onEditWhy={(why) => run(() => api.boardUpdate(managerId, item.id, { why }))}
                    onEditPlan={(patch) => run(() => api.boardUpdate(managerId, item.id, patch))}
                    onRemove={() => {
                      if (window.confirm(`Remove ${item.symbol} from Exit?`)) run(() => api.boardRemove(managerId, item.id))
                    }}
                  />
                </ReorderSlot>
              )
            })}
            {exitItems.length === 0 && <div className="myboard-empty">Drop a card here</div>}
          </div>
        </div>
      </div>
    </div>
  )
}

// Notion-style palette. Translucent so the tint reads in both light and dark themes.
const CARD_COLORS = [
  { name: 'None', value: null },
  { name: 'Red', value: 'rgba(224,49,49,0.16)' },
  { name: 'Orange', value: 'rgba(232,126,4,0.18)' },
  { name: 'Yellow', value: 'rgba(240,200,8,0.20)' },
  { name: 'Green', value: 'rgba(15,122,90,0.18)' },
  { name: 'Blue', value: 'rgba(34,113,177,0.18)' },
  { name: 'Purple', value: 'rgba(140,90,200,0.18)' },
  { name: 'Gray', value: 'rgba(120,120,120,0.18)' },
]

function ColorPicker({ color, onColor }) {
  const [open, setOpen] = useState(false)
  return (
    <span className="myboard-colorpick">
      <button
        className="myboard-colorpick-btn"
        title="Card colour"
        style={{ background: color || 'transparent' }}
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o) }}
      >{color ? '' : '○'}</button>
      {open && (
        <span className="myboard-colorpick-pop" onClick={(e) => e.stopPropagation()}>
          {CARD_COLORS.map((c) => (
            <button
              key={c.name}
              title={c.name}
              className={`myboard-swatch${!c.value ? ' myboard-swatch-none' : ''}`}
              style={c.value ? { background: c.value } : undefined}
              onClick={() => { onColor(c.value); setOpen(false) }}
            >{c.value ? '' : '⦸'}</button>
          ))}
        </span>
      )}
    </span>
  )
}

// Wraps a draggable card and turns a drop from the same column into a full insert
// reorder (before/after the target depending on where the pointer lands). Drops from a
// different column are ignored here so they bubble to the column body (status change).
function ReorderSlot({ column, itemKey, drag, onReorder, children }) {
  const [pos, setPos] = useState(null) // 'before' | 'after' | null
  const active = drag && drag.column === column && drag.key !== itemKey

  function onDragOver(e) {
    if (!active) return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    const r = e.currentTarget.getBoundingClientRect()
    setPos(e.clientY < r.top + r.height / 2 ? 'before' : 'after')
  }
  function onDrop(e) {
    if (!active) return
    e.preventDefault()
    e.stopPropagation()
    onReorder(drag.key, itemKey, pos !== 'after')
    setPos(null)
  }

  return (
    <div
      className={`myboard-slot${pos ? ' ins-' + pos : ''}`}
      onDragOver={onDragOver}
      onDragLeave={() => setPos(null)}
      onDrop={onDrop}
    >
      {children}
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

// A real, live position — draggable to Exit, with editable notes.
function HoldingCard({ row, color, onColor, onDragStart, onAddNotes }) {
  const [showClients, setShowClients] = useState(false)
  const [editingNotes, setEditingNotes] = useState(false)
  const [notes, setNotes] = useState(row.notes || '')

  function saveNotes() {
    if (onAddNotes) onAddNotes(row.symbol, notes)
    setEditingNotes(false)
  }

  return (
    <div className="myboard-card myboard-card-holding" draggable onDragStart={onDragStart} style={color ? { background: color } : undefined}>
      <div className="myboard-card-top">
        <span className="myboard-symbol">{row.symbol}</span>
        <span className="myboard-price">{row.ltp != null ? inr(row.ltp) : '—'}</span>
        <ColorPicker color={color} onColor={onColor} />
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
      {editingNotes ? (
        <div style={{ marginTop: '8px', display: 'flex', gap: '4px' }}>
          <textarea placeholder="Your notes" value={notes} onChange={(e) => setNotes(e.target.value)} style={{ flex: 1, fontSize: '12px', padding: '4px', borderRadius: '4px', border: '1px solid var(--line)', background: 'var(--surface-2)' }} rows={2} />
          <button onClick={saveNotes} style={{ padding: '4px 8px', fontSize: '12px', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>✓</button>
        </div>
      ) : (
        <button onClick={() => setEditingNotes(true)} style={{ marginTop: '8px', fontSize: '11px', background: 'transparent', color: 'var(--muted)', border: '1px solid var(--line)', borderRadius: '4px', padding: '4px 8px', cursor: 'pointer', width: '100%' }}>
          {notes ? '✏ Edit notes' : '+ Add notes'}
        </button>
      )}
      {notes && !editingNotes && <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '4px', fontStyle: 'italic' }}>{notes}</div>}
      <div className="myboard-drag-hint">drag to Exit to plan a sell</div>
    </div>
  )
}

function WatchingCard({ item, color, onColor, onDragStart, onEditWhy, onEditPlan, onRemove }) {
  return (
    <PlanCard
      item={item} color={color} onColor={onColor}
      onDragStart={onDragStart} onEditWhy={onEditWhy} onEditPlan={onEditPlan} onRemove={onRemove}
    />
  )
}

function ExitCard({ item, color, onColor, onDragStart, onEditWhy, onEditPlan, onRemove }) {
  return (
    <PlanCard
      item={item} color={color} onColor={onColor}
      onDragStart={onDragStart} onEditWhy={onEditWhy} onEditPlan={onEditPlan} onRemove={onRemove}
      footer={item.source === 'holding' && (
        <div className="myboard-actual">
          From a real holding{item.exited_price != null && <> · price when flagged {inr(item.exited_price)} on {item.exited_at}</>}
        </div>
      )}
    />
  )
}

function PlanCard({ item, color, onColor, onDragStart, onEditWhy, onEditPlan, onRemove, footer }) {
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
    <div className="myboard-card" draggable onDragStart={onDragStart} style={color ? { background: color } : undefined}>
      <div className="myboard-card-top">
        <span className="myboard-symbol">{item.symbol}</span>
        <span className="myboard-price">{item.price != null ? inr(item.price) : '—'}</span>
        <ColorPicker color={color} onColor={onColor} />
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

// Watchlist entry: card from a watchlist, draggable to Exit, with editable notes.
function WatchlistCard({ item, color, onColor, onDragStart, onAddNotes }) {
  const [editingNotes, setEditingNotes] = useState(false)
  const [notes, setNotes] = useState(item.notes || '')

  function saveNotes() {
    if (onAddNotes) onAddNotes(item.symbol, notes)
    setEditingNotes(false)
  }

  return (
    <div className="myboard-card" draggable onDragStart={onDragStart} style={color ? { background: color } : undefined}>
      <div className="myboard-card-top">
        <span className="myboard-symbol">{item.symbol}</span>
        <span className="myboard-price">{item.price != null ? inr(item.price) : '—'}</span>
        <ColorPicker color={color} onColor={onColor} />
      </div>
      <div className="myboard-plan">{inr(item.added_price || '—')} on {item.added_date}</div>
      {item.why && <div className="myboard-why" style={{ marginTop: '6px', cursor: 'default', marginBottom: 0, padding: 0, border: 'none', background: 'transparent', fontSize: '12px', color: 'var(--muted)' }}>{item.why}</div>}
      {editingNotes ? (
        <div style={{ marginTop: '8px', display: 'flex', gap: '4px' }}>
          <textarea placeholder="Your notes" value={notes} onChange={(e) => setNotes(e.target.value)} style={{ flex: 1, fontSize: '12px', padding: '4px', borderRadius: '4px', border: '1px solid var(--line)', background: 'var(--surface-2)' }} rows={2} />
          <button onClick={saveNotes} style={{ padding: '4px 8px', fontSize: '12px', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>✓</button>
        </div>
      ) : (
        <button onClick={() => setEditingNotes(true)} style={{ marginTop: '8px', fontSize: '11px', background: 'transparent', color: 'var(--muted)', border: '1px solid var(--line)', borderRadius: '4px', padding: '4px 8px', cursor: 'pointer' }}>
          {notes ? '✏ Edit notes' : '+ Add notes'}
        </button>
      )}
      {notes && !editingNotes && <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '4px', fontStyle: 'italic' }}>{notes}</div>}
      <div className="myboard-drag-hint">from watchlist • drag to Exit to plan a sale</div>
    </div>
  )
}
