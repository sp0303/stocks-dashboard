# Portfolio Intelligence v2 — Low-Level Design: Frontend (React)

**Stack:** React 19 · TypeScript 5 (strict) · Vite 6 · React Router 7 (lazy routes) · TanStack Query v5 · TanStack Table + Virtual · Zustand · Apache ECharts 5 (modular) · Tailwind CSS v4 · shadcn/ui (Radix) · lucide-react · openapi-typescript + openapi-fetch · react-hook-form + zod (forms only) · Vitest · Testing Library · MSW · Playwright
**Parent:** [HLD](HLD.md) · **Modelled on:** `quest-mf/docs/architecture/LLD-frontend.md` and `quest-mf/docs/DESIGN.md`
**Design-system choices that need your approval:** see §7 and OPEN-DECISIONS O-3, O-5.

---

## 1. Principles

1. **One component per file.** ≤ 150 lines per file, ≤ 40 lines of JSX per component. v1's `ClientDashboard.jsx` is 1,403 lines with 19 hand-rolled fetch hooks; that shape is not allowed.
2. **Feature-sliced.** `app / pages / features / components / lib / stores`. Features expose a public `index.ts`; nothing imports another feature's internals (enforced by `eslint-plugin-boundaries`).
3. **Server state ≠ client state.** TanStack Query owns server data. Zustand owns UI state. The URL owns filters and the active tab. Nothing is copied between them.
4. **Everything heavy is lazy** (routes, charts, tables, forms).
5. **Render less**: virtualised lists (> 50 rows), memoised rows, narrow store selectors, deferred values.
6. **Generated API types.** Never hand-write a response type that exists in OpenAPI.
7. **Units in one place.** All backend ratios are decimals; `lib/format/percent.ts` is the only place that multiplies by 100 (DOMAIN-RULES R12). Zero is a value, never "missing".

## 2. Folder structure

```text
apps/web/
├── index.html · vite.config.ts · tsconfig.json · eslint.config.js · .size-limit.json
└── src/
    ├── main.tsx
    ├── app/
    │   ├── providers/ (QueryProvider, ThemeProvider, AuthGate)
    │   ├── router/    (routes.tsx, RouteError.tsx, prefetch.ts)
    │   └── layout/    (AppShell, Sidebar, Topbar, CommandSearch, DisclaimerFooter)
    ├── pages/         # thin composition only; no logic, no fetching
    ├── features/
    │   ├── auth/  admin/
    │   ├── manager-book/        # overview cards, book-vs-market chart, client table, trade log, holdings roll-up
    │   ├── client/
    │   │   ├── overview/  holdings/  allocation/  performance/  trade-analytics/
    │   │   ├── dividends/  playbook/  corporate-actions/  pnl-calendar/  upload/  broker-sync/
    │   ├── stock-detail/
    │   ├── watchlist/  board/  sector-research/  screener/  orb/  data-health/
    ├── components/
    │   ├── ui/        # shadcn primitives styled with tokens
    │   ├── charts/    # EChart.tsx (the ONLY ECharts import), options/ (pure option builders), theme.ts
    │   ├── data/      # VirtualTable, NumberCell (Money, Percent, Delta), EmptyState, StalePrice
    │   └── feedback/  # PageSkeleton, CardSkeleton, ErrorCard
    ├── lib/           # api/ (openapi-fetch client, generated schema.d.ts, columnar.ts), format/, sse.ts
    ├── stores/        # authStore (in-memory token), uiStore, compareStore
    └── test/
```

## 3. Mapping from v1 components

| v1 (JSX) | Lines | v2 feature |
|---|---:|---|
| `Login.jsx`, `SuperAdmin.jsx` | — | `features/auth`, `features/admin` |
| `ManagerView.jsx`, `ManagerMetrics.jsx`, `ManagerHoldings.jsx`, `ManagerTradeLog.jsx` | — | `features/manager-book` |
| `ClientDashboard.jsx` (12 tabs) | **1,403** | `features/client/*` (one slice per tab) |
| `PnlCalendar.jsx` | — | `features/client/pnl-calendar` |
| `StockDetailDrawer.jsx`, `StockAnalysis.jsx` | — | `features/stock-detail` |
| `Watchlist.jsx`, `MyBoard.jsx` | 380 / 674 | `features/watchlist`, `features/board` |
| `SectorResearch.jsx` | 1,047 | `features/sector-research` |
| `Screener.jsx`, `pages/Orb.jsx` | 412 / 435 | `features/screener`, `features/orb` |
| `AccountManager.jsx`, `AccountSelector.jsx` | 333 | `features/client/broker-sync` |
| `CorporateActions.jsx`, `PortfolioViewer.jsx` | — | `features/client/corporate-actions`, `features/client/holdings` |
| `common.jsx` (Stat, useAsync, formatters) | — | `components/ui` + TanStack Query + `lib/format` |

## 4. Routing and lazy loading

```text
/login
/                              → manager book (or the client's own dashboard for role=client)
/clients/:clientId/:tab?       → tab ∈ overview|holdings|allocation|performance|analytics|dividends|playbook|actions|upload
/stocks/:symbol                → stock detail (also opens as a drawer)
/watchlist   /board   /research/sectors   /screener   /orb
/admin                         → super_admin only
/data-health                   → freshness of prices, benchmarks, quotes; DQ issues
```

- Every route and every tab is `React.lazy`; hover/focus on a link prefetches the chunk **and** the first query.
- The active tab is in the URL, so links are shareable and back/forward works.

### 4.1 Request budget for first paint

The client dashboard fetches **four** endpoints (`overview`, `series`, `positions`, `metrics`). Each card owns its query and skeleton, so cards stream in independently with no waterfall. Other tabs fetch when opened. (v1: 19 requests, several recomputing the same holdings.)

## 5. State management

| State | Owner | Examples |
|---|---|---|
| Server data | **TanStack Query** | overview, series, positions, playbook |
| Shareable filters, active tab, range | **URL params** | `range=1Y`, `benchmarks=nifty_50,mid_cap`, `tab=performance` |
| UI state | **Zustand** `uiStore` | sidebar, density, theme, command palette |
| Session | **Zustand** `authStore` (memory only; no tokens in `localStorage`) | access token, user |
| Forms | react-hook-form + zod | upload, manual trade, add client |

### 5.1 Query conventions

```ts
export function useSeries(clientId: string, p: SeriesParams) {
  return useQuery({
    queryKey: ["client", clientId, "series", p],   // includes as_of via the response envelope
    queryFn: ({ signal }) => api.GET("/clients/{id}/series", { params: { path: { id: clientId }, query: p }, signal }),
    placeholderData: keepPreviousData,             // no flicker when the range changes
    staleTime: 5 * 60_000,                         // the series changes at most daily, or on upload
    select: toColumnar,                            // memoised typed-array mapping for charts
  });
}
```

Defaults: `refetchOnWindowFocus: false`, `retry: 1` (0 for 4xx). Uploads and manual trades call `invalidateQueries(["client", id])`.

**Live prices** are a separate query polled every 10 s **only while the tab is visible and the market is open**; the response carries `as_of` and `stale`, and `StalePrice` renders an explicit "as of 10:32" marker instead of pretending the price is live.

## 6. Performance playbook and budgets

| Technique | Where |
|---|---|
| Route + tab lazy loading; hover prefetch | router, tab bar |
| Visibility-gated chart mount (`useInView`) | every chart card |
| `React.memo` rows, module-level column defs, TanStack Virtual (row 40 px, overscan 8) | tables > 50 rows |
| `useDeferredValue` for search; `startTransition` for sort | tables, search |
| Columnar payload → typed arrays; ECharts `sampling:'lttb'`, `animation:false` above 2 k points | charts |
| `Intl` formatters created once at module scope | `lib/format` |
| Self-hosted Geist (woff2), `font-display: swap`; hashed immutable assets | build |
| Web Worker (Comlink) to sort/aggregate > 5 k rows | trade log, playbook |

**Budgets (CI-enforced):** initial JS ≤ 150 KB gz · route chunk ≤ 80 KB gz · `echarts` chunk ≤ 250 KB gz · LCP ≤ 1.5 s · INP ≤ 200 ms · CLS ≤ 0.05.
v1 is at 62 KB gz initial, so **the budget is not a problem to fix**; it is a guard against regressions.

## 7. Design system

Adopt `quest-mf/docs/DESIGN.md`: achromatic tokens (canvas `#f5f5f5`, paper `#fff`, ink `#0a0a0a`, hairline `#e5e5e5`, ember `#e7000b`), Geist, 18 px radius for interactive elements and 24 px for cards, compact density. Tailwind v4 `@theme` copied verbatim; components use token classes only (no raw hex).

Finance-specific rules (quest-mf already documents these; v2 inherits them):

| Topic | Rule |
|---|---|
| Positive numbers | ink, with `+` and ▲ |
| Negative numbers | ember, with `−` and ▼ (the only non-destructive use of ember) |
| Colour is never the only signal | sign and glyph always present |
| Charts | monochrome series told apart by dash pattern and marker; the benchmark is always dashed grey; drawdown area is ember at 12 % |
| Tables | numeric columns right-aligned, `tabular-nums`; the table sits inside a 24 px card |
| Themes | light and dark must both work; tokens redefined under `[data-theme="dark"]` |
| Accessibility | WCAG AA, visible focus, `aria-sort`, every chart has a "view data" table fallback |

> **Decision needed (O-3):** v1 uses green/red for gains and losses. The quest-mf system deliberately does not. Adopting it gives one design language across both products but changes what users see every day. The default in this plan is to adopt it with ▲/▼ and signs; the alternative is a documented green/red extension.

### 7.1 Components

`Stat` (label, value, sub, tone), `Money`, `Percent`, `Delta`, `StalePrice`, `DataTable` (virtual), `ChartCard` (header, range tabs, "view data"), `EmptyState`, `ErrorCard` (retry), `Skeleton`, `WarningBanner` (unmatched sells, unpriced symbols, stale benchmark). **Every async component renders four states: loading, empty, error, data.**

## 8. Charts

| v1 chart (Recharts) | v2 (ECharts option builder) | Data |
|---|---|---|
| Performance vs benchmarks (line, 4 benchmarks) | `lineOption` with `dataZoom`, benchmark dashed | `series` columnar |
| Book vs market; per-client return | `lineOption` | `mser` columnar |
| Allocation (pie + legend) | `pieOption` (donut) | `allocation` |
| Equity curve + drawdown | `lineOption` + area | `trade_analytics` |
| Distribution, monthly P&L | `barOption` | `trade_analytics` |
| P&L calendar | `calendarHeatmapOption` | `pnl-calendar` |

> **Decision needed (O-5):** ECharts is chosen for canvas rendering of 800-point multi-series charts, `dataZoom`, and sharing the wrapper and theme with quest-mf. The cost is porting six Recharts charts. Keeping Recharts for the pie only is acceptable. The bundle impact is neutral (Recharts is 101 KB gz today).

## 9. API client

- `npm run gen:api` regenerates `src/lib/api/schema.d.ts` from OpenAPI; CI fails if it is stale.
- `openapi-fetch` middleware: adds `Authorization`, adds `X-Request-ID`, and on `401` performs one single-flight refresh (`POST /auth/refresh`) then replays the request once.
- Dev: Vite proxies `/api` to `http://127.0.0.1:8200`.

## 10. Testing

| Level | Tool | Target |
|---|---|---|
| Unit | Vitest | formatters (especially percent/rupee), option builders, columnar mapper, stores |
| Component | Testing Library + MSW | each feature component in all four states |
| E2E | Playwright | login → manager book → client → performance → upload a tradebook → download it |
| Visual | Playwright screenshots (light + dark) | key pages |
| A11y | axe | no serious violations |
| Perf | Lighthouse CI + size-limit | budgets in §6 |

Contract with the backend: an MSW handler set is **generated from the same OpenAPI**, so a schema change breaks a frontend test at build time, not in production.

## 11. Scripts

```json
{ "dev": "vite", "build": "tsc -b && vite build", "preview": "vite preview --port 3000",
  "lint": "eslint . && prettier --check .", "typecheck": "tsc -b --noEmit", "test": "vitest run",
  "e2e": "playwright test", "gen:api": "node scripts/gen-api.mjs", "size": "size-limit" }
```
