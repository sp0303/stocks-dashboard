# v2 UI parity vs v1, by persona

_Updated 2026-11-08 after the parity build and a local end-to-end test on real tradebooks. Replaces the 2026-09-22 report, which listed most of this as missing._

Legend: ✅ built and exercised in a browser on production-shaped data · 🟡 built, not yet exercised end to end · ❌ not built.

## Super-admin
| Feature | Status |
|---|---|
| Platform tiles (managers, clients, trades stored, AUM, P&L) | ✅ |
| Add / reassign client, add manager | ✅ dialogs open and validate · 🟡 submit paths |
| Edit / deactivate / delete (soft) manager, with confirm dialogs | ✅ confirm dialog · 🟡 server paths |
| Corporate-actions panel: stored count, refresh held, backfill NSE (Redis stream → `ca_refresh_worker`) | ✅ request accepted (202) · 🟡 worker not run against NSE |
| "View as manager" | ✅ |

## Manager
| Feature | Status |
|---|---|
| Book tiles, client roster, add / edit / delete client | ✅ tiles and roster · 🟡 client forms |
| Performance: book vs benchmarks, per-client returns | ✅ |
| Aggregated holdings by selected clients (one definition with the tiles, R5) | ✅ |
| Closed-trades log (`portfolio.round_trips`, written by `analytics_compute`) | ✅ totals equal book P&L |
| Corporate actions, Watchlists, Board (prices + stale flag) | ✅ |
| Screener, Sector R&D | 🟡 UI and empty states; needs the v1 screener sync (`v1_sync_screener`) |
| Tradebook upload: Zerodha / Groww `.xlsx` and CSV, duplicate and wrong-account protection | ✅ |

## Client
| Feature | Status |
|---|---|
| Headline cards, risk stats, XIRR, TWR NAV chart | ✅ |
| Holdings with exchange badge, "No price" / "NSE price" notes (R6, ADR-0009) | ✅ |
| Trade history, dividends (+ "Find missing dividends"), P&L calendar | ✅ · 🟡 accept-a-suggestion flow |
| Allocation, concentration, performance vs benchmarks, trade analytics, playbook + authenticated CSV | ✅ |
| Health score, beta / alpha, intraday P&L, holding highlights, manual trades | ✅ |
| Per-client corporate actions and watchlist, stock drawer + thesis | ✅ |

## Cross-cutting
| Item | Status |
|---|---|
| Light / dark theme (toggle, follows system) | ✅ |
| Dialogs close on Escape; destructive confirm focuses Cancel | ✅ |
| Session survives a reload (refresh token) | ✅ |
| Change-password dialog | ✅ opens · 🟡 success path |

## Not built / deferred
- Broker account management and portfolio sync (Kite / Angel): deferred by decision.
- ORB tab: present, out of scope for this pass.
- Frontend unit tests (no test runner in `apps/web`), virtualised long tables, URL-state for the client sub-tab.
- Demerger handling (e.g. a symbol change after a demerger leaves the holding unpriced with an R8 warning).
