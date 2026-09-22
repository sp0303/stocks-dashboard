# 0005. Frontend Stack (TypeScript, TanStack, ECharts) and Design System

* **Status**: Proposed (awaiting approval); **two sub-decisions need the user (O-3, O-5)**
* **Date**: 2026-09-21
* **Deciders**: Project Owner
* **Consulted**: `quest-mf` LLD-frontend and `docs/DESIGN.md`; `docs/v2/00-CURRENT-STATE-AUDIT.md` §7

---

## 1. Context and Problem Statement

v1's frontend is 6,811 lines of JSX with no types and a hand-rolled `useAsync` hook. `ClientDashboard.jsx` is 1,403 lines and fires 19 requests on load, several recomputing the same data. The audit shows the **bundle is not the problem** (62 KB gzip initial); structure, types and server-state handling are.

## 2. Decision

1. **React 19 + TypeScript (strict) + Vite**, feature-sliced folders, one component per file (≤ 150 lines), boundaries enforced by lint.
2. **TanStack Query** for all server state, **TanStack Table + Virtual** for lists over 50 rows, **Zustand** for UI state, the **URL** for filters and the active tab. Nothing duplicated between them.
3. **Generated API types** from OpenAPI (`openapi-typescript` + `openapi-fetch`); CI fails if stale. MSW handlers are generated from the same schema.
4. **Consolidated endpoints**: the client dashboard first-paints from four requests; other tabs load lazily.
5. **Tailwind v4 + shadcn/ui** using quest-mf's DESIGN.md tokens (18 px / 24 px radii, Geist, compact density), both themes.
6. **ECharts (modular)** behind one wrapper, series downsampled server-side (LTTB, ≤ 800 points).
7. Budgets enforced in CI: initial JS ≤ 150 KB gz, route ≤ 80 KB gz, LCP ≤ 1.5 s, INP ≤ 200 ms.
8. **Units in one place:** the UI formatter is the only code that multiplies a ratio by 100 (DOMAIN-RULES R12).

### Sub-decisions that change what users see

- **O-3, gain/loss colour.** quest-mf's system is achromatic: positive = ink with `+`/▲, negative = ember with `−`/▼. v1 uses green/red. *Default in this plan: adopt quest-mf's system for one design language across both products.* Alternative: keep green/red as a documented extension.
- **O-5, chart library.** Default: ECharts (canvas performance, `dataZoom`, shared wrapper and theme with quest-mf). Cost: porting six Recharts charts. Alternative: keep Recharts for the pie only.

## 3. Consequences

**Positive:** end-to-end types catch the class of bug where a unit or shape drifts between backend and UI; the four-request first paint removes v1's fan-out; shared tokens and components with quest-mf; long lists stay cheap.
**Negative / cost:** a full frontend rewrite (Phase 4, the largest single block of work); users see a changed UI; a learning cost for any contributor unfamiliar with TanStack Query.
**Rejected:** incremental TypeScript conversion of the JSX (keeps the structural problems); Next.js/SSR (an authenticated dashboard does not need it); Redux (boilerplate).
