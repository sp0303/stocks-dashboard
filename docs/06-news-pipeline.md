# 06 — News Pipeline (LLD)

Portfolio-aware news for managers. The differentiator is not summaries — it is **relevance**:
every news item is linked to a security and scored against what a manager's clients actually
hold. Generic feeds are a commodity; "what happened today to *your* book" is the product.

Design mirrors the existing codebase:
- **Provider interface + cache + module facade**, exactly like [`services/market_data.py`](../backend/app/services/market_data.py).
- **Async `BaseStore` twins** (Json + Mongo), exactly like [`store.py`](../backend/app/store.py).
- **`/api` routers returning `{"data": ...}`**, exactly like the existing routers.
- **Local security master** ([`services/securities.py`](../backend/app/services/securities.py)) reused for entity linking — no new source of truth.

---

## 1. Scope

**In:** RSS + NSE/BSE announcements + uploaded newspaper/broker PDFs → clean → dedupe →
entity-link to tickers → summarize + sentiment (LLM behind an interface) → rank against
holdings → serve as a portfolio morning brief and per-stock news.

**Out (later):** full-text web scraping at scale, offline model hosting (interface allows it,
we don't ship it in v1), push notifications (reuses existing scheduled-task infra when added).

**Hard privacy boundary:** client **holdings never leave the process**. The LLM sees only public
article text. Holding-matching and ranking happen locally. (See §7.)

---

## 2. Pipeline stages

```
Sources                 Pipeline (worker)                         Store            API
  RSS  ───┐         ┌─ fetch ─ clean ─ hash/dedupe ─┐          news_raw
  NSE  ───┼─ Provider ─────────────────────────────┼─ entity-link ─ news_items ─ /api/news/*
  PDF  ───┘         └─ (raw text)                   │   (securities.py)          brief/stock
                                                    └─ summarize+sentiment (LLMProvider)
```

Each stage is pure and independently testable. A stage failure degrades gracefully:
un-summarized items still show headline + link; unlinked items are dropped from portfolio
views but kept in the raw table for debugging.

---

## 3. Data model

Four collections. Field names follow existing `snake_case` + `id`/`created_at` conventions.

### `news_raw` — one row per fetched document, pre-processing
```
id                str
source_id         str          # which provider config produced it
source_type       str          # RSS | NSE | BSE | PDF | MONEYCONTROL
external_id       str | None    # provider's own id (RSS guid, NSE seq)
url               str | None
title             str
body              str          # cleaned full text (PDF page text / article body)
published_at      str          # ISO; provider time or fetch time
fetched_at        str
content_hash      str          # sha256(title+body) — dedupe key
raw_meta          dict         # provider-specific (pdf page range, feed name)
```
Index: `content_hash` (unique), `source_type`, `published_at`.

### `news_items` — the enriched, servable unit (1:1 with a deduped raw doc)
```
id                str
raw_id            str
title             str
summary           str | None   # 2–3 lines, LLM
sentiment         str | None   # POSITIVE | NEGATIVE | NEUTRAL
sentiment_score   float | None # -1..1
event_type        str | None   # EARNINGS | SPLIT | DIVIDEND | MERGER | RATING | MACRO | GENERIC
symbols           list[str]    # linked tickers (may be empty = macro/unlinked)
url               str | None
source_type       str
published_at      str
created_at        str
status            str          # NEW | SUMMARIZED | FAILED
```
Index: `symbols` (multikey), `published_at`, `status`.

### `news_links` — explicit symbol↔item edges with confidence (queryable both ways)
```
id                str
item_id           str
symbol            str
confidence        float        # 0..1 from matcher
match_method      str          # EXACT | ALIAS | FUZZY | LLM
```
Index: `symbol`, `item_id`.

### `news_sources` — provider configs (data, not code)
```
id                str
type              str          # RSS | NSE | BSE | PDF | MONEYCONTROL
name              str          # "Google News: <ticker>", "NSE Announcements"
config            dict         # url template, feed url, poll interval
enabled           bool
last_fetched_at   str | None
```

> **Why a separate `news_links` table** rather than only the `symbols` array on `news_items`:
> the array is great for "news for this stock" reads; the edge table carries **confidence +
> method** so ranking and audits can reason about *why* a link exists, and lets us tune the
> matcher without rewriting items. Both are kept in sync on write (denormalized-for-read).

---

## 4. Provider interface (ingestion)

Same ABC-then-concrete shape as `MarketDataProvider`. Providers are **sync** and run in a
`ThreadPoolExecutor` (matches the market-data code); the store layer is async.

```python
# services/news/providers.py
from __future__ import annotations
from abc import ABC, abstractmethod

class NewsProvider(ABC):
    source_type: str

    @abstractmethod
    def fetch(self, since: str | None) -> list[dict]:
        """Return raw docs: {external_id, url, title, body, published_at, raw_meta}.
        `since` lets pollers do incremental pulls. No dedupe here — pipeline owns it."""


class GoogleNewsRSSProvider(NewsProvider):
    source_type = "RSS"
    # query per held ticker: https://news.google.com/rss/search?q=<name>+stock&hl=en-IN
    # cheapest, instant coverage; headlines + short desc only.

class NSEAnnouncementsProvider(NewsProvider):
    source_type = "NSE"
    # official corporate announcements JSON — highest-trust signal
    # (results, board meetings, splits, insider trades). Maps 1:1 to a ticker already.

class PDFProvider(NewsProvider):
    source_type = "PDF"
    # PyMuPDF (fitz). Multi-column newspapers: extract by text blocks, sort by
    # (column, y) so reading order survives. One raw doc per article-ish block,
    # or per page for broker research. See §6.

class MoneycontrolRSSProvider(NewsProvider):
    source_type = "MONEYCONTROL"   # phase 2 — cross-check / corroboration
```

`PyMuPDF` (AGPL) chosen over `pypdf`: correct multi-column reading order, table/block
extraction, speed. Licensing is fine for a hosted commercial service (we don't redistribute
the library); revisit only if we ever ship it client-side.

---

## 5. Entity linking — the core value step

Turns "article mentions Reliance" into "→ RELIANCE → held by clients X, Y".

**Alias index (built once from the security master):**
```python
# services/news/linker.py
# securities.py already knows every symbol we care about. Build:
#   name/alias  -> symbol      (RELIANCE, "Reliance Industries", "RIL")
# Seed aliases from a small curated map next to securities.py; extend freely,
# same philosophy as the sector map ("Extend freely").
```

**Match cascade (cheapest first, LLM last):**
1. **EXACT** — ticker token appears verbatim → confidence 1.0.
2. **ALIAS** — known company-name/alias hit → 0.9.
3. **FUZZY** — normalized token overlap / rapidfuzz above threshold → 0.6–0.8.
4. **LLM disambiguation** — only for ambiguous hits ("Tata" → which Tata co.?) or when 1–3
   found nothing but the item is clearly single-company. Prompt returns `{symbol|null,
   confidence}`. **Only the article text is sent — never holdings.**

Items linking to **no** symbol are tagged `event_type=MACRO` and still shown in a "market"
strip, just not attributed to a stock.

---

## 6. PDF extraction detail

```python
# services/news/pdf.py  — PyMuPDF
# 1. doc = fitz.open(stream=bytes)
# 2. per page: page.get_text("blocks") -> [(x0,y0,x1,y1,text,block_no,...)]
# 3. cluster blocks into columns by x0; sort within column by y0 -> reading order
# 4. merge short adjacent blocks into article candidates (heuristic: headline = larger font
#    via "dict" spans; body = following blocks until next headline-sized span)
# 5. emit one raw doc per candidate {title, body, raw_meta:{page, bbox}}
```
Fallback: if block heuristics fail (scanned image PDF), flag `raw_meta.needs_ocr=true` and
skip — OCR is out of v1 scope. Upload endpoint returns per-article count so the manager sees
what parsed.

---

## 7. Summarization + sentiment (LLM behind interface)

Same provider pattern; **hosted first, offline swappable** — decided in the brainstorm.

```python
# services/news/llm.py
class LLMProvider(ABC):
    @abstractmethod
    def summarize(self, title: str, body: str) -> dict:
        """{summary, sentiment, sentiment_score, event_type}. Input is PUBLIC text only."""

class ClaudeProvider(LLMProvider):     # default (claude, cheap for news volume)
class OfflineProvider(LLMProvider):    # local Llama/Mistral — interface ready, not shipped v1
```

- One call per **item** (batched where the provider allows), structured JSON out.
- Cache by `content_hash` → never re-summarize the same article across managers/clients.
- **Privacy boundary is enforced by construction:** `summarize()` takes only `title, body`.
  Holdings enter the flow only later, in ranking, which is pure local arithmetic.
- Failure → item saved `status=FAILED`, still servable as headline+link.

---

## 8. Ranking (relevance = the moat)

Per manager (or per client) view, score each candidate item:

```
score =  w_hold   * held?(symbol, scope)          # 1 if any client in scope holds it
       + w_conc   * concentration_weight(symbol)   # from analytics.concentration
       + w_event  * event_weight(event_type)       # EARNINGS/SPLIT > RATING > GENERIC
       + w_sent   * abs(sentiment_score)           # strong news (either sign) ranks up
       + w_fresh  * recency_decay(published_at)     # exponential, ~24h half-life
       + w_corrob * corroboration(content group)    # multiple sources agree (phase 2)
```
Defaults `w_hold` dominant. Unheld items score low but aren't deleted (searchable). This is
the step that converts 200 articles into the 5 a manager must read — **spend effort here, not
on a better summarizer.**

---

## 9. Store additions (`BaseStore` + both twins)

```python
# raw + dedupe
async def news_raw_exists(self, content_hash: str) -> bool: ...
async def insert_news_raw(self, doc: dict) -> dict: ...

# items + links (write both, keep symbols[] and news_links in sync)
async def upsert_news_item(self, doc: dict, links: list[dict]) -> dict: ...
async def get_news_item(self, item_id: str) -> dict | None: ...
async def news_item_by_hash(self, content_hash: str) -> dict | None: ...  # summary cache

# reads
async def news_for_symbols(self, symbols: list[str], limit: int, since: str | None) -> list[dict]: ...
async def news_for_symbol(self, symbol: str, limit: int) -> list[dict]: ...

# sources
async def list_news_sources(self, enabled: bool | None = None) -> list[dict]: ...
async def touch_news_source(self, source_id: str, ts: str) -> None: ...
```
Mongo: multikey index on `news_items.symbols`, unique on `news_raw.content_hash`. Json twin
mirrors with in-memory filters (same as existing trade dedupe via `file_hash`).

---

## 10. API (router `news.py`, prefix `/api`)

```
GET  /api/news/brief?manager_id=&limit=      # ranked portfolio brief for a manager
GET  /api/news/client/{client_id}?limit=     # ranked for one client's book
GET  /api/news/stock/{symbol}?limit=         # per-stock feed (bolts onto StockAnalysis)
GET  /api/news/watch?client_id=              # "what to watch": upcoming earnings/ex-div/splits
POST /api/news/pdf?scope=manager|client&id=  # upload newspaper/broker PDF (multipart)
POST /api/news/refresh                       # manual trigger of the poll (admin/dev)
GET  /api/news/sources  |  POST /api/news/sources   # manage provider configs
```
All return `{"data": ...}`. `brief`/`client`/`stock` resolve holdings locally, then read
`news_for_symbols`, then rank (§8). PDF upload reuses the multipart pattern from
`clients.py` tradebook upload (hash → dedupe → parse → pipeline).

---

## 11. Scheduling / worker

v1: an **interval poller** (asyncio task on app startup, or a `POST /refresh` cron) that, per
enabled source, calls `provider.fetch(since=last_fetched_at)` → pipeline. NSE announcements
~every 15 min during market hours; RSS ~30 min; PDF is on-demand (upload-triggered). When the
platform gains the background-job/scheduled-task infra from the roadmap, move this there; the
pipeline function stays identical (it's already decoupled from *how* it's invoked).

Poll target set = **union of held tickers across active clients** + a curated market/macro
feed. No point fetching news for stocks nobody owns.

---

## 12. Caching, dedupe, degradation

- **Dedupe** at ingest by `content_hash`; the same wire story from 3 outlets collapses to one
  item with multiple `source_type`s recorded (feeds corroboration score).
- **Summary cache** by `content_hash` — cross-tenant, since article text is public. Biggest
  cost saver.
- **Quote-style TTL** on `brief`/`stock` responses (reuse `QUOTE_CACHE_TTL` idea) so dashboard
  reads don't re-rank every hit.
- **Degradation ladder:** LLM down → headline+link. Linker miss → macro strip. Provider down →
  last good items served with `stale` flag (same convention as `market_data` quotes).

---

## 13. Config additions (`config.py`)

```ini
NEWS_ENABLED=true
NEWS_POLL_SECONDS=1800
NEWS_LLM_PROVIDER=claude        # claude | offline
ANTHROPIC_API_KEY=              # required when provider=claude
NEWS_MAX_ITEMS_PER_SYMBOL=20
NEWS_SUMMARY_CACHE_TTL=86400
```

---

## 14. Testing (mirror the DB-free engine tests)

- **linker**: alias/fuzzy cascade on fixture headlines → expected symbols + method (pure, no I/O).
- **pdf**: fixture 2-column newspaper page → ordered article blocks.
- **ranking**: given held/concentration/event fixtures → expected order (pure).
- **dedupe**: same story twice → one item, two source_types.
- **providers**: mocked HTTP → raw-doc shape.
- **llm**: `OfflineProvider`/stub so summarization tests need no network (same discipline as
  `engine.py` being DB-free).

---

## 15. Build order (smallest shippable first)

1. **Store methods + `news_raw`/`news_items`/`news_links`** and the pipeline skeleton.
2. **GoogleNewsRSS + NSE providers**, `linker` against `securities.py`.
3. **ClaudeProvider** summarize+sentiment, summary cache.
4. **`/api/news/stock/{symbol}`** → bolt onto existing `StockAnalysis.jsx` (fastest visible win).
5. **Ranking + `/api/news/brief`** → the morning-brief screen.
6. **PDF upload**, then **`/watch`** (upcoming events).
7. Phase 2: Moneycontrol corroboration, offline provider, push alerts.

Skip offline models and heavy scraping until the RSS+NSE loop earns its keep.
