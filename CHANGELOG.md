# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); this project uses [semantic
versioning](https://semver.org/).

## [0.2.0] — 2026-09-01

### Added
- **Multiple named watchlists per manager.** A manager can keep up to **10** named
  watchlists, switch between them with a tab bar, rename them inline (double-click or
  ✎), and delete them (🗑, blocked on the last remaining list). Clients keep their
  single watchlist unchanged.
- **Watchlist sorting** by Symbol (name) and Price — click the column header to sort,
  click again to flip direction (▲/▼). Rows without a price always sort last.
- **Watchlist pagination** at 10 symbols per page, with Prev/Next controls and a
  "Page X of Y · N symbols" indicator. Resets to page 1 on list switch, sort change,
  or add/remove.
- Store tests for the multi-list watchlist model (migration, per-list isolation,
  rename/delete, default-list resolution, persistence).

### Changed
- **Watchlist detail moved into the right-side drawer.** The per-symbol tracking
  fields — *Added on*, *Added @ ₹*, *Alert date*, *Target ₹* — moved out of the table
  into an editable Details panel in the stock drawer, leaving a leaner table (Symbol ·
  Price · Day change · Since added · Why · Sector). *Added @* is now correctable.
- Watchlist entries are now stored as one-or-more named lists per owner
  (`{owner_type, owner_id, lists: [{id, name, entries}]}`); legacy single-list docs
  migrate transparently to a "Watchlist 1" default. Entry operations take an optional
  `watchlist_id` (defaults to the owner's first/default list), so client and
  email-alert paths keep working unchanged.
- The email-alert sweep now evaluates every named list under an owner.

### Fixed
- `requirements.txt` was missing the Angel One SmartAPI runtime dependencies
  (`smartapi-python`, `PyOTP`, and its under-declared transitive deps `logzero`,
  `websocket-client`), so live market data failed on a clean deploy with
  `No module named 'SmartApi'` / `'logzero'`. All are now pinned.
- OCR test (`test_upside_down_page_is_recovered_by_ocr`) now **skips** when the
  Tesseract binary isn't installed instead of failing, so the suite is green on dev
  boxes while still running OCR on CI / the server.

## [0.1.0]

- Initial portfolio-intelligence dashboard: super-admin / manager / client personas,
  tradebook ingestion + dedupe, positions & analytics (XIRR/CAGR, benchmark overlay,
  dividend tracking), watchlists with target/date email alerts, sector research, and
  Angel One SmartAPI + Yahoo market data.
