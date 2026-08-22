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
  // watchlists — scope: 'managers' | 'clients'
  watchlist: (scope, id) => req(`/api/${scope}/${id}/watchlist`).then((r) => r.data),
  watchlistAdd: (scope, id, symbol) =>
    req(`/api/${scope}/${id}/watchlist`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ symbol }),
    }).then((r) => r.data),
  watchlistRemove: (scope, id, symbol) =>
    req(`/api/${scope}/${id}/watchlist/${symbol}`, { method: 'DELETE' }).then((r) => r.data),
  history: (symbol, from, interval = '1d') =>
    req(`/api/market/history/${symbol}?from=${from}&interval=${interval}`).then((r) => r.data),
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
  // news pipeline
  uploadNewsPdf: (scope, id, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return req(`/api/news/pdf?scope=${scope}&id=${id}`, { method: 'POST', body: fd }).then((r) => r.data)
  },
  newsPdfUpload: (uploadId) => req(`/api/news/pdf-uploads/${uploadId}`).then((r) => r.data),
  newsPdfUploads: (scope, id) => req(`/api/news/pdf-uploads?scope=${scope}&id=${id}`).then((r) => r.data),
  newsForStock: (symbol, limit = 20) => req(`/api/news/stock/${symbol}?limit=${limit}`).then((r) => r.data),
  newsForClient: (clientId, limit = 50) => req(`/api/news/client/${clientId}?limit=${limit}`).then((r) => r.data),
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
