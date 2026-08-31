// Single API client. In dev, Vite proxies /api -> backend :8010.
// For GitHub Pages, set VITE_API_BASE to the deployed backend (Cloudflare tunnel) URL.
const BASE = import.meta.env.VITE_API_BASE || ''

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, opts)
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try { msg = (await res.json()).detail || msg } catch { /* ignore */ }
    throw new Error(msg)
  }
  return res.json()
}

// Base path for a watchlist's entries: a specific named list when wlId is given
// (managers), otherwise the owner's single default list (clients / legacy).
const _wlEntries = (scope, id, wlId) =>
  wlId ? `/api/${scope}/${id}/watchlists/${wlId}/entries` : `/api/${scope}/${id}/watchlist`

export const api = {
  health: () => req('/api/health'),
  overview: () => req('/api/admin/overview').then((r) => r.data),
  managers: () => req('/api/admin/managers').then((r) => r.data),
  createManager: (body) =>
    req('/api/admin/managers', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }).then((r) => r.data),
  updateManager: (id, body) =>
    req(`/api/admin/managers/${id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }).then((r) => r.data),
  deleteManager: (id) => req(`/api/admin/managers/${id}`, { method: 'DELETE' }).then((r) => r.data),
  clients: (managerId) =>
    req(managerId ? `/api/managers/${managerId}/clients` : '/api/clients').then((r) => r.data),
  createClient: (body) =>
    req('/api/clients', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }).then((r) => r.data),
  updateClient: (id, body) =>
    req(`/api/clients/${id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }).then((r) => r.data),
  deleteClient: (id) => req(`/api/clients/${id}`, { method: 'DELETE' }).then((r) => r.data),
  // watchlists — scope: 'managers' | 'clients'. Entry ops take an optional wlId to
  // address a specific named list (managers); without it they hit the owner's single
  // default list (clients, and the legacy per-owner endpoint).
  watchlist: (scope, id, wlId) => req(_wlEntries(scope, id, wlId)).then((r) => r.data),
  watchlistAdd: (scope, id, symbol, { why, alertDate, alertPrice, addedDate, remarks, risks, sector } = {}, wlId) =>
    req(_wlEntries(scope, id, wlId), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        symbol, why: why || undefined, alert_date: alertDate || undefined,
        alert_price: alertPrice ?? undefined, added_date: addedDate || undefined,
        remarks: remarks || undefined, risks: risks || undefined, sector: sector || undefined,
      }),
    }).then((r) => r.data),
  // Only the keys passed here are sent (and thus updated) — the backend uses
  // exclude_unset, so an explicit '' / null clears a field rather than being ignored.
  watchlistUpdate: (scope, id, symbol, patch = {}, wlId) => {
    const body = {}
    if ('why' in patch) body.why = patch.why
    if ('alertDate' in patch) body.alert_date = patch.alertDate
    if ('alertPrice' in patch) body.alert_price = patch.alertPrice
    if ('addedDate' in patch) body.added_date = patch.addedDate
    if ('addedPrice' in patch) body.added_price = patch.addedPrice
    if ('remarks' in patch) body.remarks = patch.remarks
    if ('risks' in patch) body.risks = patch.risks
    if ('sector' in patch) body.sector = patch.sector
    return req(`${_wlEntries(scope, id, wlId)}/${symbol}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then((r) => r.data)
  },
  watchlistRemove: (scope, id, symbol, wlId) =>
    req(`${_wlEntries(scope, id, wlId)}/${symbol}`, { method: 'DELETE' }).then((r) => r.data),
  // Named-list management (managers). Returns [{id, name, count}] (or the created/renamed one).
  watchlistLists: (scope, id) => req(`/api/${scope}/${id}/watchlists`).then((r) => r.data),
  watchlistListCreate: (scope, id, name) =>
    req(`/api/${scope}/${id}/watchlists`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }),
    }).then((r) => r.data),
  watchlistListRename: (scope, id, wlId, name) =>
    req(`/api/${scope}/${id}/watchlists/${wlId}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }),
    }).then((r) => r.data),
  watchlistListDelete: (scope, id, wlId) =>
    req(`/api/${scope}/${id}/watchlists/${wlId}`, { method: 'DELETE' }).then((r) => r.data),
  // broker (market-data) connectivity
  angelStatus: () => req('/api/angel/status').then((r) => r.data),
  // email alerts
  alertsStatus: () => req('/api/alerts/status'),
  alertsTest: (to) =>
    req('/api/alerts/test', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ to }),
    }),
  alertsCheckNow: () => req('/api/alerts/check', { method: 'POST' }),
  history: (symbol, from, interval = '1d') =>
    req(`/api/market/history/${symbol}?from=${from}&interval=${interval}`).then((r) => r.data),
  sectorHotels: () => req('/api/sectors/hotels').then((r) => r.data),
  sectorHotelsPriceMatrix: () => req('/api/sectors/hotels/price-matrix').then((r) => r.data),
  managerMetrics: (id) => req(`/api/managers/${id}/metrics`).then((r) => r.data),
  uploadTradebook: (clientId, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return req(`/api/clients/${clientId}/tradebooks`, { method: 'POST', body: fd }).then((r) => r.data)
  },
  uploads: (clientId) => req(`/api/clients/${clientId}/tradebooks`).then((r) => r.data),
  portfolio: (clientId) => req(`/api/clients/${clientId}/portfolio`).then((r) => r.data),
  holdings: (clientId) => req(`/api/clients/${clientId}/holdings`).then((r) => r.data),
  allocation: (clientId, by, basis = 'current') =>
    req(`/api/clients/${clientId}/allocation?by=${by}&basis=${basis}`).then((r) => r.data),
  concentration: (clientId) => req(`/api/clients/${clientId}/concentration`).then((r) => r.data),
  performance: (clientId) => req(`/api/clients/${clientId}/performance`).then((r) => r.data),
  xirr: (clientId) => req(`/api/clients/${clientId}/xirr`).then((r) => r.data),
  holdingSummary: (clientId) => req(`/api/clients/${clientId}/holding-summary`).then((r) => r.data),
  holdingSummaryNarrative: (clientId) => req(`/api/clients/${clientId}/holding-summary/narrative`).then((r) => r.data),
  dividends: (clientId) => req(`/api/clients/${clientId}/dividends`).then((r) => r.data),
  createDividend: (clientId, body) =>
    req(`/api/clients/${clientId}/dividends`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }).then((r) => r.data),
  updateDividend: (clientId, divId, body) =>
    req(`/api/clients/${clientId}/dividends/${divId}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }).then((r) => r.data),
  deleteDividend: (clientId, divId) =>
    req(`/api/clients/${clientId}/dividends/${divId}`, { method: 'DELETE' }).then((r) => r.data),
  dividendSuggestions: (clientId, symbol) =>
    req(`/api/clients/${clientId}/dividends/suggestions${symbol ? `?symbol=${symbol}` : ''}`).then((r) => r.data),
  trades: (clientId, { tag } = {}) =>
    req(`/api/clients/${clientId}/trades${tag ? `?tag=${tag}` : ''}`).then((r) => r),
  tags: (clientId) => req(`/api/clients/${clientId}/tags`).then((r) => r.data),
  createTag: (clientId, body) =>
    req(`/api/clients/${clientId}/tags`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }).then((r) => r.data),
  deleteTag: (clientId, tagId) =>
    req(`/api/clients/${clientId}/tags/${tagId}`, { method: 'DELETE' }).then((r) => r.data),
  setTradeTags: (clientId, fingerprint, tagIds) =>
    req(`/api/clients/${clientId}/trades/${fingerprint}/tags`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tag_ids: tagIds }),
    }).then((r) => r.data),
  setTradeNote: (clientId, fingerprint, note) =>
    req(`/api/clients/${clientId}/trades/${fingerprint}/note`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ note }),
    }).then((r) => r.data),
  stock: (clientId, symbol) => req(`/api/clients/${clientId}/stocks/${symbol}`).then((r) => r.data),
  // opening/adjustment trades for shares not in the tradebook (IPO/bonus/pre-window)
  manualTrades: (clientId) => req(`/api/clients/${clientId}/manual-trades`).then((r) => r.data),
  addManualTrade: (clientId, body) =>
    req(`/api/clients/${clientId}/manual-trades`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }).then((r) => r.data),
  deleteManualTrade: (clientId, fingerprint) =>
    req(`/api/clients/${clientId}/manual-trades/${fingerprint}`, { method: 'DELETE' }).then((r) => r.data),
  playbook: (clientId, { sort = 'sell_date', order = 'desc', symbol, page = 1, pageSize = 10 } = {}) =>
    req(
      `/api/clients/${clientId}/playbook?sort=${sort}&order=${order}&page=${page}&page_size=${pageSize}${symbol ? `&symbol=${symbol}` : ''}`
    ).then((r) => r),
  playbookByStock: (clientId) => req(`/api/clients/${clientId}/playbook/by-stock`).then((r) => r.data),
}

// ── formatting helpers ──────────────────────────────────────────────
export const inr = (n) => {
  if (n === null || n === undefined) return '—'
  const abs = Math.abs(n)
  if (abs >= 1e7) return `₹${(n / 1e7).toFixed(2)}Cr`
  if (abs >= 1e5) return `₹${(n / 1e5).toFixed(2)}L`
  if (abs >= 1e3) return `₹${(n / 1e3).toFixed(1)}K`
  return `₹${Number(n).toFixed(0)}`
}
export const inrFull = (n) =>
  n === null || n === undefined ? '—' : '₹' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })
export const pct = (n) => (n === null || n === undefined ? '—' : `${n > 0 ? '+' : ''}${Number(n).toFixed(2)}%`)
// plain percentage with no +/- sign — for weights/shares, not gains
export const pctPlain = (n) => (n === null || n === undefined ? '—' : `${Number(n).toFixed(2)}%`)
