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

    # watchlists  (owner_type: "MANAGER" | "CLIENT")
    async def get_watchlist(self, owner_type: str, owner_id: str) -> list[str]: ...
    async def add_watchlist_symbol(self, owner_type: str, owner_id: str, symbol: str) -> list[str]: ...
    async def remove_watchlist_symbol(self, owner_type: str, owner_id: str, symbol: str) -> list[str]: ...

    # uploads + trades
    async def create_upload(self, doc: dict) -> dict: ...
    async def list_uploads(self, client_id: str) -> list[dict]: ...
    async def upload_exists(self, client_id: str, file_hash: str) -> bool: ...
    async def next_upload_version(self, client_id: str) -> int: ...
    async def insert_trades(self, trades: list[dict]) -> tuple[int, int]: ...
    async def list_trades(self, client_id: str) -> list[dict]: ...
    async def count_trades(self, client_id: str) -> int: ...

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
        }

    async def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self._db = json.loads(self.path.read_text() or "{}")
            for k in ("managers", "clients", "uploads", "trades", "watchlists", "tags", "trade_tags", "dividends"):
                self._db.setdefault(k, [])
            self._db.setdefault("benchmark_prices", {})

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

    async def get_watchlist(self, owner_type, owner_id):
        w = self._wl(owner_type, owner_id)
        return list(w["symbols"]) if w else []

    async def add_watchlist_symbol(self, owner_type, owner_id, symbol):
        symbol = symbol.upper()
        async with self._lock:
            w = self._wl(owner_type, owner_id)
            if not w:
                w = {"owner_type": owner_type, "owner_id": owner_id, "symbols": []}
                self._db["watchlists"].append(w)
            if symbol not in w["symbols"]:
                w["symbols"].append(symbol)
            self._flush()
            return list(w["symbols"])

    async def remove_watchlist_symbol(self, owner_type, owner_id, symbol):
        symbol = symbol.upper()
        async with self._lock:
            w = self._wl(owner_type, owner_id)
            if w and symbol in w["symbols"]:
                w["symbols"].remove(symbol)
                self._flush()
            return list(w["symbols"]) if w else []

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
            self._flush()
        return inserted, dupes

    async def list_trades(self, client_id):
        return [t for t in self._db["trades"] if t["client_id"] == client_id]

    async def count_trades(self, client_id):
        return sum(1 for t in self._db["trades"] if t["client_id"] == client_id)

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

    async def get_watchlist(self, owner_type, owner_id):
        w = await self.db.watchlists.find_one({"owner_type": owner_type, "owner_id": owner_id})
        if not w:
            return []
        if "symbols" in w:
            return list(w["symbols"])
        if "entries" in w:
            return [e["symbol"] for e in w["entries"] if isinstance(e, dict) and "symbol" in e]
        return []

    async def add_watchlist_symbol(self, owner_type, owner_id, symbol):
        symbol = symbol.upper()
        # Find if the watchlist exists and has 'entries'
        w = await self.db.watchlists.find_one({"owner_type": owner_type, "owner_id": owner_id})
        if w and "entries" in w:
            # If it uses the 'entries' schema, add to entries
            if not any(isinstance(e, dict) and e.get("symbol") == symbol for e in w["entries"]):
                await self.db.watchlists.update_one(
                    {"owner_type": owner_type, "owner_id": owner_id},
                    {"$push": {"entries": {"symbol": symbol, "checkpoint_date": None}}}
                )
        else:
            # Otherwise use the default 'symbols' schema
            await self.db.watchlists.update_one(
                {"owner_type": owner_type, "owner_id": owner_id},
                {"$addToSet": {"symbols": symbol}},
                upsert=True,
            )
        return await self.get_watchlist(owner_type, owner_id)

    async def remove_watchlist_symbol(self, owner_type, owner_id, symbol):
        symbol = symbol.upper()
        await self.db.watchlists.update_one(
            {"owner_type": owner_type, "owner_id": owner_id},
            {
                "$pull": {
                    "symbols": symbol,
                    "entries": {"symbol": symbol}
                }
            }
        )
        return await self.get_watchlist(owner_type, owner_id)

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
