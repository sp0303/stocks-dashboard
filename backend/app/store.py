"""Storage abstraction with two interchangeable backends.

- MongoStore  : used when MONGODB_URL is set (motor / async).
- JsonStore   : file-backed fallback so the whole app runs and is testable with no DB.

Both expose the same async API. Swap happens automatically at startup based on config,
so paste the Mongo URL into .env later and nothing else changes.

Entities: managers, clients, tradebook_uploads, trades. Positions/analytics are derived
on the fly, not persisted (Phase-1 simplicity).
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

from app.config import settings


def _new_id() -> str:
    return uuid.uuid4().hex[:24]


# Free-text / value fields on a watchlist entry that are editable after add time
# via update_watchlist_entry. sector is a manual override of the classifier's guess
# (None → fall back to the security master); alert_price is a target/trigger price.
_EDITABLE_ENTRY_FIELDS = (
    "why", "alert_date", "remarks", "risks", "added_date", "added_price", "sector", "alert_price",
    # internal bookkeeping for the email-alert sender (not exposed on the API model):
    # the target value / date already emailed about, so we notify each threshold once.
    "alert_price_notified", "alert_date_notified",
)


def _normalize_watchlist_entries(doc: dict | None) -> list[dict]:
    """A watchlist doc predates the entries schema (bare "symbols" list) or already
    uses it. Either way, normalize to the full entry shape so callers never see the
    difference. `checkpoint_date` was an earlier, never-populated stand-in for
    `added_date` — folded in here so any of that data isn't silently dropped."""
    if not doc:
        return []
    if "entries" in doc:
        return [
            {
                "symbol": e["symbol"],
                "added_date": e.get("added_date") or e.get("checkpoint_date"),
                "added_price": e.get("added_price"),
                "why": e.get("why") or "",
                "alert_date": e.get("alert_date"),
                "alert_price": e.get("alert_price"),
                "alert_price_notified": e.get("alert_price_notified"),
                "alert_date_notified": e.get("alert_date_notified"),
                "sector": e.get("sector"),
                "remarks": e.get("remarks") or "",
                "risks": e.get("risks") or "",
            }
            for e in doc["entries"]
            if isinstance(e, dict) and "symbol" in e
        ]
    if "symbols" in doc:
        return [
            {
                "symbol": s, "added_date": None, "added_price": None, "why": "", "alert_date": None,
                "alert_price": None, "alert_price_notified": None, "alert_date_notified": None,
                "sector": None, "remarks": "", "risks": "",
            }
            for s in doc["symbols"]
        ]
    return []


def _normalize_watchlist_lists(doc: dict | None) -> list[dict]:
    """Normalize a watchlist doc to the multi-list shape: [{id, name, entries}].

    Handles the historical shapes transparently:
      * new    — doc["lists"] = [{id, name, entries:[...]}]
      * legacy — doc["entries"] / doc["symbols"] (one unnamed list)
    A migrated legacy list is surfaced with the stable id "default" so its identity is
    consistent across reads even before it's rewritten in the new shape on the next edit."""
    if not doc:
        return []
    if "lists" in doc:
        out = []
        for l in doc["lists"]:
            if not isinstance(l, dict):
                continue
            out.append({
                "id": l.get("id") or _new_id(),
                "name": l.get("name") or "Watchlist",
                "entries": _normalize_watchlist_entries({"entries": l.get("entries", [])}),
            })
        return out
    if "entries" in doc or "symbols" in doc:
        return [{"id": "default", "name": "Watchlist 1", "entries": _normalize_watchlist_entries(doc)}]
    return []


class BaseStore:
    async def init(self) -> None: ...
    async def close(self) -> None: ...

    # managers
    async def list_managers(self) -> list[dict]: ...
    async def get_manager(self, mid: str) -> dict | None: ...
    async def create_manager(self, doc: dict) -> dict: ...
    async def update_manager(self, mid: str, patch: dict) -> dict | None: ...
    async def delete_manager(self, mid: str) -> bool: ...

    # clients
    async def list_clients(self, manager_id: str | None = None) -> list[dict]: ...
    async def get_client(self, cid: str) -> dict | None: ...
    async def get_client_by_code(self, code: str) -> dict | None: ...
    async def create_client(self, doc: dict) -> dict: ...
    async def update_client(self, cid: str, patch: dict) -> dict | None: ...
    async def delete_client(self, cid: str) -> bool: ...

    # watchlists  (owner_type: "MANAGER" | "CLIENT"). Each entry is
    # {symbol, added_date, added_price, why, alert_date, remarks, risks} —
    # added_date/added_price are captured once at add time (added_price comes from
    # the caller, since store.py does no network I/O); why/alert_date/remarks/risks
    # are editable afterwards via update_watchlist_entry. why is a short one-liner
    # shown inline in the table; remarks is a longer free-form note and risks a
    # short risk callout, both surfaced as tabs in the stock detail drawer.
    # A watchlist doc holds one *or more* named lists per owner:
    #   {owner_type, owner_id, lists: [{id, name, entries:[...]}]}.
    # get_watchlists returns the list metadata+entries; the entry ops take an optional
    # watchlist_id (None → the owner's first/default list, so single-list callers such
    # as clients and the alert sweep keep working unchanged).
    async def get_watchlists(self, owner_type: str, owner_id: str) -> list[dict]: ...
    async def list_watchlists(self, owner_type: str, owner_id: str) -> list[dict]: ...
    async def create_watchlist(self, owner_type: str, owner_id: str, name: str) -> dict: ...
    async def rename_watchlist(self, owner_type: str, owner_id: str, watchlist_id: str, name: str) -> dict | None: ...
    async def delete_watchlist(self, owner_type: str, owner_id: str, watchlist_id: str) -> bool: ...
    async def get_watchlist(self, owner_type: str, owner_id: str, watchlist_id: str | None = None) -> list[dict]: ...
    async def add_watchlist_symbol(
        self, owner_type: str, owner_id: str, symbol: str,
        added_price: float | None = None, why: str | None = None, alert_date: str | None = None,
        added_date: str | None = None, remarks: str | None = None, risks: str | None = None,
        sector: str | None = None, alert_price: float | None = None, watchlist_id: str | None = None,
    ) -> list[dict]: ...
    async def update_watchlist_entry(self, owner_type: str, owner_id: str, symbol: str, patch: dict, watchlist_id: str | None = None) -> list[dict]: ...
    async def remove_watchlist_symbol(self, owner_type: str, owner_id: str, symbol: str, watchlist_id: str | None = None) -> list[dict]: ...

    # uploads + trades
    async def create_upload(self, doc: dict) -> dict: ...
    async def list_uploads(self, client_id: str) -> list[dict]: ...
    async def upload_exists(self, client_id: str, file_hash: str) -> bool: ...
    async def next_upload_version(self, client_id: str) -> int: ...
    async def insert_trades(self, trades: list[dict]) -> tuple[int, int]: ...
    async def list_trades(self, client_id: str) -> list[dict]: ...
    async def count_trades(self, client_id: str) -> int: ...
    async def delete_trade(self, client_id: str, fingerprint: str) -> bool: ...

    # trade journal — Zerodha-Console-style tags: reusable, named, colored labels
    # defined once per client and applied to any number of trades. The rationale for
    # a strategy lives on the tag (name/color/description), not retyped per trade.
    async def list_tags(self, client_id: str) -> list[dict]: ...
    async def create_tag(self, doc: dict) -> dict: ...
    async def update_tag(self, client_id: str, tag_id: str, patch: dict) -> dict | None: ...
    async def delete_tag(self, client_id: str, tag_id: str) -> bool: ...

    # trade <-> tag assignment + a free-text note, keyed off fingerprint (not the
    # Mongo/JSON "id") since fingerprint is the stable, deterministic identity of a
    # trade row that survives re-imports. Tags are the reusable "what kind of trade
    # was this"; the note is the one-off "why, specifically, this time".
    async def get_trade_journal(self, client_id: str) -> dict[str, dict]: ...
    async def set_trade_tags(self, client_id: str, fingerprint: str, tag_ids: list[str]) -> dict: ...
    async def set_trade_note(self, client_id: str, fingerprint: str, note: str) -> dict: ...

    # dividends — persisted once entered/accepted; never re-fetched from the market
    # data provider once stored (see analytics.dividends suggestions flow).
    async def list_dividends(self, client_id: str) -> list[dict]: ...
    async def create_dividend(self, doc: dict) -> dict: ...
    async def update_dividend(self, client_id: str, div_id: str, patch: dict) -> dict | None: ...
    async def delete_dividend(self, client_id: str, div_id: str) -> bool: ...

    # benchmark index price cache (date -> close), keyed by index symbol, so the
    # Performance chart doesn't hit the market data provider on every load.
    async def get_benchmark_prices(self, symbol: str) -> dict[str, float]: ...
    async def save_benchmark_prices(self, symbol: str, prices: dict[str, float]) -> None: ...

    # corporate actions — GLOBAL (not per-client), keyed by ISIN/symbol. Splits/bonuses/
    # demergers/buybacks fetched from NSE (see services/corporate_actions.py) and deduped
    # on a stable `key`. The FIFO engine consumes split/bonus rows to keep held quantities
    # correct across a corporate action that isn't a trade.
    async def save_corporate_actions(self, records: list[dict]) -> int: ...
    async def list_corporate_actions(
        self, isins: list[str] | None = None, symbols: list[str] | None = None
    ) -> list[dict]: ...
    async def corporate_actions_coverage(self) -> dict: ...

    # stock thesis — investment rationale, catalysts, risks, etc.
    async def get_stock_thesis(self, client_id: str, symbol: str) -> dict | None: ...
    async def save_stock_thesis(self, client_id: str, symbol: str, thesis: dict) -> dict: ...


# --------------------------------------------------------------------------- #
# JSON fallback
# --------------------------------------------------------------------------- #
class JsonStore(BaseStore):
    def __init__(self, data_dir: str):
        self.path = Path(data_dir) / "store.json"
        self._lock = asyncio.Lock()
        self._db = {
            "managers": [], "clients": [], "uploads": [], "trades": [], "watchlists": [],
            "tags": [], "trade_tags": [], "dividends": [], "benchmark_prices": {},
            "corporate_actions": [], "classifications": {}, "thesis": {},
        }

    async def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self._db = json.loads(self.path.read_text() or "{}")
            for k in ("managers", "clients", "uploads", "trades", "watchlists", "tags",
                      "trade_tags", "dividends", "corporate_actions"):
                self._db.setdefault(k, [])
            self._db.setdefault("benchmark_prices", {})
            self._db.setdefault("classifications", {})
            self._db.setdefault("thesis", {})

        # Initialize classification cache with persisted data
        from app.services import securities
        securities.init_cache(self._db.get("classifications", {}))

    def _flush(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._db, default=str))
        os.replace(tmp, self.path)

    async def list_managers(self):
        return list(self._db["managers"])

    async def get_manager(self, mid):
        return next((m for m in self._db["managers"] if m["id"] == mid), None)

    async def create_manager(self, doc):
        doc["id"] = doc.get("id") or _new_id()
        async with self._lock:
            self._db["managers"].append(doc)
            self._flush()
        return doc

    async def update_manager(self, mid, patch):
        async with self._lock:
            m = await self.get_manager(mid)
            if not m:
                return None
            m.update(patch)
            self._flush()
            return m

    async def delete_manager(self, mid):
        async with self._lock:
            before = len(self._db["managers"])
            self._db["managers"] = [m for m in self._db["managers"] if m["id"] != mid]
            self._db["watchlists"] = [
                w for w in self._db["watchlists"]
                if not (w["owner_type"] == "MANAGER" and w["owner_id"] == mid)
            ]
            self._flush()
            return len(self._db["managers"]) < before

    async def list_clients(self, manager_id=None):
        cs = self._db["clients"]
        return [c for c in cs if manager_id is None or c["portfolio_manager_id"] == manager_id]

    async def get_client(self, cid):
        return next((c for c in self._db["clients"] if c["id"] == cid), None)

    async def get_client_by_code(self, code):
        return next((c for c in self._db["clients"] if c.get("client_code") == code), None)

    async def create_client(self, doc):
        doc["id"] = doc.get("id") or _new_id()
        async with self._lock:
            self._db["clients"].append(doc)
            self._flush()
        return doc

    async def update_client(self, cid, patch):
        async with self._lock:
            c = await self.get_client(cid)
            if not c:
                return None
            c.update(patch)
            self._flush()
            return c

    async def delete_client(self, cid):
        async with self._lock:
            before = len(self._db["clients"])
            self._db["clients"] = [c for c in self._db["clients"] if c["id"] != cid]
            # cascade: trades, uploads, watchlist
            self._db["trades"] = [t for t in self._db["trades"] if t["client_id"] != cid]
            self._db["uploads"] = [u for u in self._db["uploads"] if u["client_id"] != cid]
            self._db["watchlists"] = [
                w for w in self._db["watchlists"]
                if not (w["owner_type"] == "CLIENT" and w["owner_id"] == cid)
            ]
            self._db["tags"] = [t for t in self._db["tags"] if t["client_id"] != cid]
            self._db["trade_tags"] = [t for t in self._db["trade_tags"] if t["client_id"] != cid]
            self._db["dividends"] = [d for d in self._db["dividends"] if d["client_id"] != cid]
            self._flush()
            return len(self._db["clients"]) < before

    def _wl(self, owner_type, owner_id):
        return next(
            (w for w in self._db["watchlists"]
             if w["owner_type"] == owner_type and w["owner_id"] == owner_id),
            None,
        )

    def _wl_doc(self, owner_type, owner_id):
        """Return the owner's watchlist doc in multi-list shape, migrating a legacy
        single-list doc in place and creating an empty doc if none exists. Caller holds
        the lock and flushes."""
        doc = self._wl(owner_type, owner_id)
        if not doc:
            doc = {"owner_type": owner_type, "owner_id": owner_id, "lists": []}
            self._db["watchlists"].append(doc)
        if "lists" not in doc:
            doc["lists"] = _normalize_watchlist_lists(doc)
            doc.pop("entries", None)
            doc.pop("symbols", None)
        return doc

    @staticmethod
    def _pick_list(doc, watchlist_id, create_default=False):
        lists = doc["lists"]
        if watchlist_id:
            return next((l for l in lists if l["id"] == watchlist_id), None)
        if lists:
            return lists[0]
        if create_default:
            l = {"id": "default", "name": "Watchlist 1", "entries": []}
            lists.append(l)
            return l
        return None

    async def get_watchlists(self, owner_type, owner_id):
        return _normalize_watchlist_lists(self._wl(owner_type, owner_id))

    async def list_watchlists(self, owner_type, owner_id):
        async with self._lock:
            doc = self._wl_doc(owner_type, owner_id)
            if not doc["lists"]:
                doc["lists"].append({"id": "default", "name": "Watchlist 1", "entries": []})
            self._flush()
            return [{"id": l["id"], "name": l["name"], "count": len(l["entries"])} for l in doc["lists"]]

    async def create_watchlist(self, owner_type, owner_id, name):
        async with self._lock:
            doc = self._wl_doc(owner_type, owner_id)
            l = {"id": _new_id(), "name": name, "entries": []}
            doc["lists"].append(l)
            self._flush()
            return {"id": l["id"], "name": l["name"], "count": 0}

    async def rename_watchlist(self, owner_type, owner_id, watchlist_id, name):
        async with self._lock:
            doc = self._wl_doc(owner_type, owner_id)
            l = next((x for x in doc["lists"] if x["id"] == watchlist_id), None)
            if not l:
                return None
            l["name"] = name
            self._flush()
            return {"id": l["id"], "name": l["name"], "count": len(l["entries"])}

    async def delete_watchlist(self, owner_type, owner_id, watchlist_id):
        async with self._lock:
            doc = self._wl_doc(owner_type, owner_id)
            before = len(doc["lists"])
            doc["lists"] = [x for x in doc["lists"] if x["id"] != watchlist_id]
            self._flush()
            return len(doc["lists"]) < before

    async def get_watchlist(self, owner_type, owner_id, watchlist_id=None):
        lists = _normalize_watchlist_lists(self._wl(owner_type, owner_id))
        if watchlist_id:
            l = next((x for x in lists if x["id"] == watchlist_id), None)
        else:
            l = lists[0] if lists else None
        return l["entries"] if l else []

    async def add_watchlist_symbol(self, owner_type, owner_id, symbol, added_price=None, why=None, alert_date=None, added_date=None, remarks=None, risks=None, sector=None, alert_price=None, watchlist_id=None):
        from datetime import date

        symbol = symbol.upper()
        async with self._lock:
            doc = self._wl_doc(owner_type, owner_id)
            l = self._pick_list(doc, watchlist_id, create_default=True)
            if l is None:
                return []
            entries = l["entries"]
            if not any(e["symbol"] == symbol for e in entries):
                entries.append({
                    "symbol": symbol,
                    "added_date": added_date or date.today().isoformat(),
                    "added_price": added_price,
                    "why": why or "",
                    "alert_date": alert_date,
                    "alert_price": alert_price,
                    "sector": sector or None,
                    "remarks": remarks or "",
                    "risks": risks or "",
                })
            self._flush()
            return entries

    async def update_watchlist_entry(self, owner_type, owner_id, symbol, patch, watchlist_id=None):
        symbol = symbol.upper()
        async with self._lock:
            if not self._wl(owner_type, owner_id):
                return []
            doc = self._wl_doc(owner_type, owner_id)
            l = self._pick_list(doc, watchlist_id)
            if l is None:
                return []
            for e in l["entries"]:
                if e["symbol"] == symbol:
                    for k in _EDITABLE_ENTRY_FIELDS:
                        if k in patch:
                            e[k] = patch[k]
            self._flush()
            return l["entries"]

    async def remove_watchlist_symbol(self, owner_type, owner_id, symbol, watchlist_id=None):
        symbol = symbol.upper()
        async with self._lock:
            if not self._wl(owner_type, owner_id):
                return []
            doc = self._wl_doc(owner_type, owner_id)
            l = self._pick_list(doc, watchlist_id)
            if l is None:
                return []
            l["entries"] = [e for e in l["entries"] if e["symbol"] != symbol]
            self._flush()
            return l["entries"]

    async def create_upload(self, doc):
        doc["id"] = doc.get("id") or _new_id()
        async with self._lock:
            self._db["uploads"].append(doc)
            self._flush()
        return doc

    async def list_uploads(self, client_id):
        return sorted(
            [u for u in self._db["uploads"] if u["client_id"] == client_id],
            key=lambda u: u.get("version", 0),
            reverse=True,
        )

    async def upload_exists(self, client_id, file_hash):
        return any(
            u["client_id"] == client_id and u.get("file_hash") == file_hash
            for u in self._db["uploads"]
        )

    async def next_upload_version(self, client_id):
        vs = [u.get("version", 0) for u in self._db["uploads"] if u["client_id"] == client_id]
        return (max(vs) + 1) if vs else 1

    async def insert_trades(self, trades):
        existing = {
            (t["client_id"], t["fingerprint"])
            for t in self._db["trades"]
        }
        inserted = dupes = 0
        async with self._lock:
            for t in trades:
                key = (t["client_id"], t["fingerprint"])
                if key in existing:
                    dupes += 1
                    continue
                t["id"] = _new_id()
                self._db["trades"].append(t)
                existing.add(key)
                inserted += 1
            # Persist any new classifications from auto-lookup
            self._persist_classifications()
            self._flush()
        return inserted, dupes

    def _persist_classifications(self):
        """Persist the in-memory classification cache back to store."""
        from app.services import securities
        self._db["classifications"] = securities.get_cache()

    async def list_trades(self, client_id):
        return [t for t in self._db["trades"] if t["client_id"] == client_id]

    async def count_trades(self, client_id):
        return sum(1 for t in self._db["trades"] if t["client_id"] == client_id)

    async def delete_trade(self, client_id, fingerprint):
        async with self._lock:
            before = len(self._db["trades"])
            self._db["trades"] = [
                t for t in self._db["trades"]
                if not (t["client_id"] == client_id and t.get("fingerprint") == fingerprint)
            ]
            self._flush()
            return len(self._db["trades"]) < before

    async def list_tags(self, client_id):
        return [t for t in self._db["tags"] if t["client_id"] == client_id]

    async def create_tag(self, doc):
        doc["id"] = doc.get("id") or _new_id()
        async with self._lock:
            self._db["tags"].append(doc)
            self._flush()
        return doc

    async def update_tag(self, client_id, tag_id, patch):
        async with self._lock:
            tag = next(
                (t for t in self._db["tags"] if t["client_id"] == client_id and t["id"] == tag_id),
                None,
            )
            if tag:
                tag.update(patch)
                self._flush()
            return tag

    async def delete_tag(self, client_id, tag_id):
        async with self._lock:
            before = len(self._db["tags"])
            self._db["tags"] = [
                t for t in self._db["tags"]
                if not (t["client_id"] == client_id and t["id"] == tag_id)
            ]
            for link in self._db["trade_tags"]:
                if link["client_id"] == client_id and tag_id in link.get("tag_ids", []):
                    link["tag_ids"].remove(tag_id)
            self._flush()
            return len(self._db["tags"]) < before

    async def get_trade_journal(self, client_id):
        return {
            link["fingerprint"]: {"tag_ids": link.get("tag_ids", []), "note": link.get("note", "")}
            for link in self._db["trade_tags"]
            if link["client_id"] == client_id
        }

    def _trade_link(self, client_id, fingerprint):
        link = next(
            (t for t in self._db["trade_tags"]
             if t["client_id"] == client_id and t["fingerprint"] == fingerprint),
            None,
        )
        if not link:
            link = {"id": _new_id(), "client_id": client_id, "fingerprint": fingerprint, "tag_ids": [], "note": ""}
            self._db["trade_tags"].append(link)
        return link

    async def set_trade_tags(self, client_id, fingerprint, tag_ids):
        async with self._lock:
            link = self._trade_link(client_id, fingerprint)
            link["tag_ids"] = list(tag_ids)
            self._flush()
            return {"tag_ids": link["tag_ids"], "note": link.get("note", "")}

    async def set_trade_note(self, client_id, fingerprint, note):
        async with self._lock:
            link = self._trade_link(client_id, fingerprint)
            link["note"] = note
            self._flush()
            return {"tag_ids": link.get("tag_ids", []), "note": link["note"]}

    async def list_dividends(self, client_id):
        return [d for d in self._db["dividends"] if d["client_id"] == client_id]

    async def create_dividend(self, doc):
        doc["id"] = doc.get("id") or _new_id()
        async with self._lock:
            self._db["dividends"].append(doc)
            self._flush()
        return doc

    async def update_dividend(self, client_id, div_id, patch):
        async with self._lock:
            d = next(
                (d for d in self._db["dividends"] if d["client_id"] == client_id and d["id"] == div_id),
                None,
            )
            if d:
                d.update(patch)
                self._flush()
            return d

    async def delete_dividend(self, client_id, div_id):
        async with self._lock:
            before = len(self._db["dividends"])
            self._db["dividends"] = [
                d for d in self._db["dividends"]
                if not (d["client_id"] == client_id and d["id"] == div_id)
            ]
            self._flush()
            return len(self._db["dividends"]) < before

    async def get_benchmark_prices(self, symbol):
        return dict(self._db["benchmark_prices"].get(symbol, {}))

    async def save_benchmark_prices(self, symbol, prices):
        async with self._lock:
            existing = self._db["benchmark_prices"].setdefault(symbol, {})
            existing.update(prices)
            self._flush()

    async def save_corporate_actions(self, records):
        if not records:
            return 0
        async with self._lock:
            existing = {r.get("key"): r for r in self._db["corporate_actions"]}
            added = 0
            for r in records:
                k = r.get("key")
                if not k:
                    continue
                if k not in existing:
                    added += 1
                existing[k] = r  # upsert: refresh in place, keep newest fetch
            self._db["corporate_actions"] = list(existing.values())
            self._flush()
            return added

    async def list_corporate_actions(self, isins=None, symbols=None):
        rows = self._db["corporate_actions"]
        if isins is None and symbols is None:
            return list(rows)
        iset = {i for i in (isins or []) if i}
        sset = {s.upper() for s in (symbols or []) if s}
        return [r for r in rows
                if (r.get("isin") in iset) or ((r.get("symbol") or "").upper() in sset)]

    async def corporate_actions_coverage(self):
        rows = self._db["corporate_actions"]
        syms = {r.get("symbol") for r in rows if r.get("symbol")}
        return {"total": len(rows), "symbols": len(syms)}

    async def get_stock_thesis(self, client_id: str, symbol: str):
        thesis_key = f"{client_id}:{symbol}"
        return self._db.get("thesis", {}).get(thesis_key)

    async def save_stock_thesis(self, client_id: str, symbol: str, thesis: dict):
        thesis_key = f"{client_id}:{symbol}"
        async with self._lock:
            if "thesis" not in self._db:
                self._db["thesis"] = {}
            self._db["thesis"][thesis_key] = thesis
            self._flush()
        return thesis


# --------------------------------------------------------------------------- #
# Mongo backend
# --------------------------------------------------------------------------- #
class MongoStore(BaseStore):
    def __init__(self, url: str, dbname: str):
        self.url = url
        self.dbname = dbname
        self.client = None
        self.db = None

    async def init(self):
        from motor.motor_asyncio import AsyncIOMotorClient

        self.client = AsyncIOMotorClient(self.url)
        self.db = self.client[self.dbname]
        await self.db.trades.create_index(
            [("client_id", 1), ("fingerprint", 1)], unique=True
        )
        await self.db.clients.create_index("client_code")
        await self.db.uploads.create_index([("client_id", 1), ("version", -1)])
        await self.db.watchlists.create_index(
            [("owner_type", 1), ("owner_id", 1)], unique=True
        )
        await self.db.trade_tags.create_index(
            [("client_id", 1), ("fingerprint", 1)], unique=True
        )
        await self.db.tags.create_index([("client_id", 1)])
        await self.db.dividends.create_index([("client_id", 1), ("symbol", 1)])
        await self.db.benchmark_prices.create_index([("symbol", 1), ("date", 1)], unique=True)
        await self.db.corporate_actions.create_index("key", unique=True)
        await self.db.corporate_actions.create_index([("isin", 1)])
        await self.db.corporate_actions.create_index([("symbol", 1)])

    async def close(self):
        if self.client:
            self.client.close()

    @staticmethod
    def _clean(doc):
        if doc:
            doc.pop("_id", None)
        return doc

    async def list_managers(self):
        return [self._clean(d) async for d in self.db.managers.find()]

    async def get_manager(self, mid):
        return self._clean(await self.db.managers.find_one({"id": mid}))

    async def create_manager(self, doc):
        doc["id"] = doc.get("id") or _new_id()
        await self.db.managers.insert_one(dict(doc))
        return self._clean(doc)

    async def update_manager(self, mid, patch):
        await self.db.managers.update_one({"id": mid}, {"$set": patch})
        return await self.get_manager(mid)

    async def delete_manager(self, mid):
        res = await self.db.managers.delete_one({"id": mid})
        await self.db.watchlists.delete_many({"owner_type": "MANAGER", "owner_id": mid})
        return res.deleted_count > 0

    async def list_clients(self, manager_id=None):
        q = {} if manager_id is None else {"portfolio_manager_id": manager_id}
        return [self._clean(d) async for d in self.db.clients.find(q)]

    async def get_client(self, cid):
        return self._clean(await self.db.clients.find_one({"id": cid}))

    async def get_client_by_code(self, code):
        return self._clean(await self.db.clients.find_one({"client_code": code}))

    async def create_client(self, doc):
        doc["id"] = doc.get("id") or _new_id()
        await self.db.clients.insert_one(dict(doc))
        return self._clean(doc)

    async def update_client(self, cid, patch):
        await self.db.clients.update_one({"id": cid}, {"$set": patch})
        return await self.get_client(cid)

    async def delete_client(self, cid):
        res = await self.db.clients.delete_one({"id": cid})
        await self.db.trades.delete_many({"client_id": cid})
        await self.db.uploads.delete_many({"client_id": cid})
        await self.db.watchlists.delete_many({"owner_type": "CLIENT", "owner_id": cid})
        await self.db.tags.delete_many({"client_id": cid})
        await self.db.trade_tags.delete_many({"client_id": cid})
        await self.db.dividends.delete_many({"client_id": cid})
        return res.deleted_count > 0

    async def _find_lists(self, owner_type, owner_id):
        w = await self.db.watchlists.find_one({"owner_type": owner_type, "owner_id": owner_id})
        return _normalize_watchlist_lists(w)

    async def _save_lists(self, owner_type, owner_id, lists):
        await self.db.watchlists.update_one(
            {"owner_type": owner_type, "owner_id": owner_id},
            {"$set": {"owner_type": owner_type, "owner_id": owner_id, "lists": lists},
             "$unset": {"entries": "", "symbols": ""}},
            upsert=True,
        )

    @staticmethod
    def _pick_list(lists, watchlist_id, create_default=False):
        if watchlist_id:
            return next((l for l in lists if l["id"] == watchlist_id), None)
        if lists:
            return lists[0]
        if create_default:
            l = {"id": "default", "name": "Watchlist 1", "entries": []}
            lists.append(l)
            return l
        return None

    async def get_watchlists(self, owner_type, owner_id):
        return await self._find_lists(owner_type, owner_id)

    async def list_watchlists(self, owner_type, owner_id):
        lists = await self._find_lists(owner_type, owner_id)
        if not lists:
            lists = [{"id": "default", "name": "Watchlist 1", "entries": []}]
        await self._save_lists(owner_type, owner_id, lists)
        return [{"id": l["id"], "name": l["name"], "count": len(l["entries"])} for l in lists]

    async def create_watchlist(self, owner_type, owner_id, name):
        lists = await self._find_lists(owner_type, owner_id)
        l = {"id": _new_id(), "name": name, "entries": []}
        lists.append(l)
        await self._save_lists(owner_type, owner_id, lists)
        return {"id": l["id"], "name": l["name"], "count": 0}

    async def rename_watchlist(self, owner_type, owner_id, watchlist_id, name):
        lists = await self._find_lists(owner_type, owner_id)
        l = next((x for x in lists if x["id"] == watchlist_id), None)
        if not l:
            return None
        l["name"] = name
        await self._save_lists(owner_type, owner_id, lists)
        return {"id": l["id"], "name": l["name"], "count": len(l["entries"])}

    async def delete_watchlist(self, owner_type, owner_id, watchlist_id):
        lists = await self._find_lists(owner_type, owner_id)
        new = [x for x in lists if x["id"] != watchlist_id]
        if len(new) == len(lists):
            return False
        await self._save_lists(owner_type, owner_id, new)
        return True

    async def get_watchlist(self, owner_type, owner_id, watchlist_id=None):
        lists = await self._find_lists(owner_type, owner_id)
        l = self._pick_list(lists, watchlist_id)
        return l["entries"] if l else []

    async def add_watchlist_symbol(self, owner_type, owner_id, symbol, added_price=None, why=None, alert_date=None, added_date=None, remarks=None, risks=None, sector=None, alert_price=None, watchlist_id=None):
        from datetime import date

        symbol = symbol.upper()
        lists = await self._find_lists(owner_type, owner_id)
        l = self._pick_list(lists, watchlist_id, create_default=True)
        if not any(e["symbol"] == symbol for e in l["entries"]):
            l["entries"].append({
                "symbol": symbol,
                "added_date": added_date or date.today().isoformat(),
                "added_price": added_price,
                "why": why or "",
                "alert_date": alert_date,
                "alert_price": alert_price,
                "sector": sector or None,
                "remarks": remarks or "",
                "risks": risks or "",
            })
        await self._save_lists(owner_type, owner_id, lists)
        return l["entries"]

    async def update_watchlist_entry(self, owner_type, owner_id, symbol, patch, watchlist_id=None):
        symbol = symbol.upper()
        lists = await self._find_lists(owner_type, owner_id)
        l = self._pick_list(lists, watchlist_id)
        if l is None:
            return []
        for e in l["entries"]:
            if e["symbol"] == symbol:
                for k in _EDITABLE_ENTRY_FIELDS:
                    if k in patch:
                        e[k] = patch[k]
        await self._save_lists(owner_type, owner_id, lists)
        return l["entries"]

    async def remove_watchlist_symbol(self, owner_type, owner_id, symbol, watchlist_id=None):
        symbol = symbol.upper()
        lists = await self._find_lists(owner_type, owner_id)
        l = self._pick_list(lists, watchlist_id)
        if l is None:
            return []
        l["entries"] = [e for e in l["entries"] if e["symbol"] != symbol]
        await self._save_lists(owner_type, owner_id, lists)
        return l["entries"]

    async def create_upload(self, doc):
        doc["id"] = doc.get("id") or _new_id()
        await self.db.uploads.insert_one(dict(doc))
        return self._clean(doc)

    async def list_uploads(self, client_id):
        cur = self.db.uploads.find({"client_id": client_id}).sort("version", -1)
        return [self._clean(d) async for d in cur]

    async def upload_exists(self, client_id, file_hash):
        return await self.db.uploads.find_one(
            {"client_id": client_id, "file_hash": file_hash}
        ) is not None

    async def next_upload_version(self, client_id):
        last = await self.db.uploads.find_one(
            {"client_id": client_id}, sort=[("version", -1)]
        )
        return (last["version"] + 1) if last else 1

    async def insert_trades(self, trades):
        from pymongo import InsertOne
        from pymongo.errors import BulkWriteError

        if not trades:
            return 0, 0
        for t in trades:
            t["id"] = _new_id()
        ops = [InsertOne(dict(t)) for t in trades]
        try:
            res = await self.db.trades.bulk_write(ops, ordered=False)
            return res.inserted_count, 0
        except BulkWriteError as bwe:
            dupes = sum(1 for e in bwe.details.get("writeErrors", []) if e["code"] == 11000)
            inserted = bwe.details.get("nInserted", len(trades) - dupes)
            return inserted, dupes

    async def list_trades(self, client_id):
        return [self._clean(d) async for d in self.db.trades.find({"client_id": client_id})]

    async def count_trades(self, client_id):
        return await self.db.trades.count_documents({"client_id": client_id})

    async def delete_trade(self, client_id, fingerprint):
        res = await self.db.trades.delete_one({"client_id": client_id, "fingerprint": fingerprint})
        return res.deleted_count > 0

    async def list_tags(self, client_id):
        return [self._clean(d) async for d in self.db.tags.find({"client_id": client_id})]

    async def create_tag(self, doc):
        doc["id"] = doc.get("id") or _new_id()
        await self.db.tags.insert_one(dict(doc))
        return self._clean(doc)

    async def update_tag(self, client_id, tag_id, patch):
        await self.db.tags.update_one({"client_id": client_id, "id": tag_id}, {"$set": patch})
        return self._clean(await self.db.tags.find_one({"client_id": client_id, "id": tag_id}))

    async def delete_tag(self, client_id, tag_id):
        res = await self.db.tags.delete_one({"client_id": client_id, "id": tag_id})
        await self.db.trade_tags.update_many(
            {"client_id": client_id}, {"$pull": {"tag_ids": tag_id}}
        )
        return res.deleted_count > 0

    async def get_trade_journal(self, client_id):
        cur = self.db.trade_tags.find({"client_id": client_id})
        return {
            d["fingerprint"]: {"tag_ids": d.get("tag_ids", []), "note": d.get("note", "")}
            async for d in cur
        }

    async def set_trade_tags(self, client_id, fingerprint, tag_ids):
        await self.db.trade_tags.update_one(
            {"client_id": client_id, "fingerprint": fingerprint},
            {
                "$set": {"tag_ids": list(tag_ids)},
                "$setOnInsert": {"client_id": client_id, "fingerprint": fingerprint, "note": ""},
            },
            upsert=True,
        )
        d = await self.db.trade_tags.find_one({"client_id": client_id, "fingerprint": fingerprint})
        return {"tag_ids": d.get("tag_ids", []), "note": d.get("note", "")}

    async def set_trade_note(self, client_id, fingerprint, note):
        await self.db.trade_tags.update_one(
            {"client_id": client_id, "fingerprint": fingerprint},
            {
                "$set": {"note": note},
                "$setOnInsert": {"client_id": client_id, "fingerprint": fingerprint, "tag_ids": []},
            },
            upsert=True,
        )
        d = await self.db.trade_tags.find_one({"client_id": client_id, "fingerprint": fingerprint})
        return {"tag_ids": d.get("tag_ids", []), "note": d.get("note", "")}

    async def list_dividends(self, client_id):
        return [self._clean(d) async for d in self.db.dividends.find({"client_id": client_id})]

    async def create_dividend(self, doc):
        doc["id"] = doc.get("id") or _new_id()
        await self.db.dividends.insert_one(dict(doc))
        return self._clean(doc)

    async def update_dividend(self, client_id, div_id, patch):
        await self.db.dividends.update_one({"client_id": client_id, "id": div_id}, {"$set": patch})
        return self._clean(await self.db.dividends.find_one({"client_id": client_id, "id": div_id}))

    async def delete_dividend(self, client_id, div_id):
        res = await self.db.dividends.delete_one({"client_id": client_id, "id": div_id})
        return res.deleted_count > 0

    async def get_benchmark_prices(self, symbol):
        cur = self.db.benchmark_prices.find({"symbol": symbol})
        return {d["date"]: d["close"] async for d in cur}

    async def save_benchmark_prices(self, symbol, prices):
        from pymongo import UpdateOne

        if not prices:
            return
        ops = [
            UpdateOne(
                {"symbol": symbol, "date": d},
                {"$set": {"symbol": symbol, "date": d, "close": c}},
                upsert=True,
            )
            for d, c in prices.items()
        ]
        await self.db.benchmark_prices.bulk_write(ops, ordered=False)

    async def save_corporate_actions(self, records):
        from pymongo import UpdateOne

        records = [r for r in records if r.get("key")]
        if not records:
            return 0
        ops = [UpdateOne({"key": r["key"]}, {"$set": dict(r)}, upsert=True) for r in records]
        res = await self.db.corporate_actions.bulk_write(ops, ordered=False)
        return res.upserted_count

    async def list_corporate_actions(self, isins=None, symbols=None):
        if isins is None and symbols is None:
            return [self._clean(d) async for d in self.db.corporate_actions.find()]
        ors = []
        iset = [i for i in (isins or []) if i]
        sset = [s.upper() for s in (symbols or []) if s]
        if iset:
            ors.append({"isin": {"$in": iset}})
        if sset:
            ors.append({"symbol": {"$in": sset}})
        if not ors:
            return []
        return [self._clean(d) async for d in self.db.corporate_actions.find({"$or": ors})]

    async def corporate_actions_coverage(self):
        total = await self.db.corporate_actions.count_documents({})
        syms = await self.db.corporate_actions.distinct("symbol")
        return {"total": total, "symbols": len([s for s in syms if s])}

    async def get_stock_thesis(self, client_id: str, symbol: str):
        result = await self.db.thesis.find_one({"client_id": client_id, "symbol": symbol})
        return self._clean(result) if result else None

    async def save_stock_thesis(self, client_id: str, symbol: str, thesis: dict):
        doc = {"client_id": client_id, "symbol": symbol, **thesis}
        result = await self.db.thesis.update_one(
            {"client_id": client_id, "symbol": symbol},
            {"$set": doc},
            upsert=True
        )
        return doc


# --------------------------------------------------------------------------- #
_store: BaseStore | None = None


def get_store() -> BaseStore:
    assert _store is not None, "store not initialized"
    return _store


async def init_store() -> BaseStore:
    global _store
    if settings.use_mongo:
        _store = MongoStore(settings.mongodb_url, settings.mongodb_db)
    else:
        _store = JsonStore(settings.data_dir)
    await _store.init()
    return _store
