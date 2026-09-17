import React, { useMemo, useState } from 'react'
import { api, inr, inrFull, pct, pctPlain } from '../api.js'
import { Loading, ErrorBox, useAsync } from './common.jsx'
import './MyBoard.css'

// Watching and Exit are manual planning lanes (board items in the store). Holding is
// never stored here — it's real, live data from the tradebook (the same aggregation
// that powers the Holdings-by-client view), so it can't be dragged into or edited.

function pnlPct(item) {
  if (item.entry_price == null || item.price == null) return null
  return ((item.price - item.entry_price) / item.entry_price) * 100
}

export default function MyBoard({ managerId }) {
  // clients/board/holdings all fire in parallel on mount — none waits on another.
  // selectedClientIds stays null ("all, unfiltered") until the user actually touches
  // a checkbox, so the first holdings fetch never has to wait for the client list.
  const clients = useAsync(() => api.clients(managerId), [managerId])
  const [selectedClientIds, setSelectedClientIds] = useState(null)
  const allClients = clients.data || []
  const displaySelected = selectedClientIds ?? allClients.map((c) => c.id) // for checkbox display only

  const [reload, setReload] = useState(0)
  const board = useAsync(() => api.board(managerId), [managerId, reload])
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

  const watchingItems = (board.data || []).filter((i) => i.status === 'watching')
  const exitItems = (board.data || []).filter((i) => i.status === 'exit')
  const holdingRows = holdings.data?.holdings || []

  // Drag payload is JSON: {origin: 'watching' | 'exit' | 'holding', ...}
  function onDragStartWatching(e, item) {
    e.dataTransfer.setData('application/json', JSON.stringify({ origin: 'watching', itemId: item.id }))
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
    } else if (p.origin === 'holding') {
      await run(async () => {
        const items = await api.boardAdd(managerId, {
          symbol: p.symbol, entryPrice: p.buyAvg ?? undefined, source: 'holding',
        })
        const created = items[items.length - 1]
        await api.boardUpdate(managerId, created.id, { status: 'exit' })
      })
    }
    // dropping an exit card back onto itself is a no-op
  }

  async function onDropWatching(e) {
    e.preventDefault()
    setDragOverWatching(false)
    const p = readPayload(e)
    if (!p || p.origin !== 'exit') return // a real holding never demotes to a typed idea
    await run(() => api.boardUpdate(managerId, p.itemId, { status: 'watching' }))
  }

  if (board.loading || clients.loading) return <Loading what="board" />
  if (board.error) return <ErrorBox error={board.error} />
  if (clients.error) return <ErrorBox error={clients.error} />

  return (
    <div className="myboard">
      <div className="myboard-head">
        <h2>MyBoard</h2>
        <button className="myboard-add-btn" onClick={() => setAdding(true)}>+ Add idea</button>
      </div>
      {err && <div className="warn-banner">{err}</div>}

      <div className="myboard-clientbar">
        <label className="myboard-client-chip myboard-client-all">
          <input type="checkbox" checked={displaySelected.length === allClients.length && allClients.length > 0} onChange={toggleAllClients} />
          All clients ({displaySelected.length}/{allClients.length})
        </label>
        {allClients.map((c) => (
          <label key={c.id} className="myboard-client-chip">
            <input type="checkbox" checked={displaySelected.includes(c.id)} onChange={() => toggleClient(c.id)} />
            {c.name}
          </label>
        ))}
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
          <div className="myboard-col-hint">Ideas you typed in — drag to Exit to abandon</div>
          <div
            className={`myboard-col-body${dragOverWatching ? ' drag-over' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragOverWatching(true) }}
            onDragLeave={() => setDragOverWatching(false)}
            onDrop={onDropWatching}
          >
            {watchingItems.map((item) => (
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
            ))}
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
                  <div className="myboard-empty">{displaySelected.length === 0 ? 'Select at least one client' : 'No open positions'}</div>
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
