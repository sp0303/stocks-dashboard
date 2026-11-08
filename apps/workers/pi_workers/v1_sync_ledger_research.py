"""Planner for the research side of the ledger resync: theses, watchlists (+ entries), board.

Split out of ``v1_sync_ledger_plan`` (module size limit, AGENTS §3.14). Pure; v1 wins on
changed values (v1 is the system of record until cutover); nothing is ever removed --
v2 rows without a v1 source are reported as orphans.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from pi_workers.v1_sync_ledger_map import (
    BOARD_LANES,
    Result,
    dec,
    jsonable,
    parse_date,
    text,
)

if TYPE_CHECKING:
    from pi_workers.v1_sync_ledger_plan import NewId, Plan, V2Snapshot

_ENTRY_FIELDS = ("added_date", "added_price", "why", "remarks", "risks", "sector", "alert_price", "alert_date")
_BOARD_FIELDS = ("lane", "entry_price", "exit_price", "why", "sort_order")


def map_thesis(doc: dict, client_id: Any) -> Result:
    symbol = (text(doc.get("symbol")) or "").upper()
    if not symbol:
        return None, "missing_symbol"
    body = {k: v for k, v in jsonable(doc).items() if k not in ("_id", "client_id", "symbol")}
    return {"client_id": client_id, "symbol": symbol, "thesis": body}, None


def watchlist_lists(doc: dict) -> list[dict]:
    """[{name, entries}] from the multi-list shape or the legacy entries/symbols shape."""
    lists = doc.get("lists")
    if lists is None and ("entries" in doc or "symbols" in doc):
        entries = doc.get("entries") or [{"symbol": s} for s in doc.get("symbols") or []]
        lists = [{"name": "Watchlist 1", "entries": entries}]
    out = []
    for lst in lists or []:
        if isinstance(lst, dict):
            out.append({"name": text(lst.get("name")) or "Watchlist", "entries": lst.get("entries") or []})
    return out


def map_watch_entry(e: Any) -> Result:
    if not isinstance(e, dict) or not text(e.get("symbol")):
        return None, "missing_symbol"
    return {
        "symbol": str(e["symbol"]).strip().upper(),
        "added_date": parse_date(e.get("added_date") or e.get("checkpoint_date")),
        "added_price": dec(e.get("added_price"), "0.0001"),
        "why": text(e.get("why")),
        "remarks": text(e.get("remarks")),
        "risks": text(e.get("risks")),
        "sector": text(e.get("sector")),
        "alert_price": dec(e.get("alert_price"), "0.0001"),
        "alert_date": parse_date(e.get("alert_date")),
    }, None


def map_board_item(item: Any, sort_order: int) -> Result:
    if not isinstance(item, dict) or not text(item.get("symbol")):
        return None, "missing_symbol"
    lane = BOARD_LANES.get(str(item.get("status") or "watching").strip().lower())
    if lane is None:
        return None, "bad_lane"
    return {
        "symbol": str(item["symbol"]).strip().upper(),
        "lane": lane,
        "entry_price": dec(item.get("entry_price"), "0.0001"),
        "exit_price": dec(item.get("exit_price"), "0.0001"),
        "why": text(item.get("why")),
        "sort_order": sort_order,
    }, None


def owner_uuid(plan: Plan, owner_type: Any, owner_id: Any) -> tuple[str, Any]:
    ot = str(owner_type or "").strip().upper()
    src = plan.manager_map if ot == "MANAGER" else plan.client_map if ot == "CLIENT" else {}
    return ot, src.get(str(owner_id))


def plan_theses(plan: Plan, docs: list[dict], v2: V2Snapshot) -> None:
    from pi_workers.v1_sync_ledger_plan import diff

    p = plan["stock_theses"]
    by_key = {(t["client_id"], t["symbol"]): t for t in v2.theses}
    seen: set[tuple] = set()
    for doc in docs:
        cu = plan.client_map.get(str(doc.get("client_id")))
        if cu is None:
            plan.reject("stock_theses", doc, "unknown_client")
            continue
        row, why = map_thesis(doc, cu)
        if row is None:
            plan.reject("stock_theses", doc, why or "invalid")
            continue
        k = (cu, row["symbol"])
        if k in seen:
            plan.reject("stock_theses", doc, "duplicate_symbol")
            continue
        seen.add(k)
        ex = by_key.get(k)
        if ex is None:
            p.inserts.append(row)
        elif diff(ex, row, ("thesis",)):
            p.updates.append(row)
        else:
            p.unchanged += 1
    v1_clients = set(plan.client_map.values())
    p.orphans = [{"client_id": k[0], "symbol": k[1]} for k in by_key if k not in seen and k[0] in v1_clients]


def plan_watchlists(plan: Plan, docs: list[dict], v2: V2Snapshot, today: date, new_id: NewId) -> None:
    pw, pe = plan["watchlists"], plan["watchlist_entries"]
    lists = {(w["owner_type"].upper(), w["owner_id"], w["name"]): w["watchlist_id"] for w in v2.watchlists}
    entries = {(e["watchlist_id"], e["symbol"]): e for e in v2.watchlist_entries}
    seen_lists: set[Any] = set()
    seen_entries: set[tuple] = set()
    owners: set[tuple] = set()
    for doc in docs:
        ot, ou = owner_uuid(plan, doc.get("owner_type"), doc.get("owner_id"))
        if ou is None:
            plan.reject("watchlists", doc, "unknown_owner")
            continue
        owners.add((ot, ou))
        for i, lst in enumerate(watchlist_lists(doc)):
            key = (ot, ou, lst["name"])
            wid = lists.get(key)
            if wid in seen_lists:
                plan.reject("watchlists", doc, "duplicate_list_name")
                continue
            if wid is None:
                wid = new_id()
                lists[key] = wid
                pw.inserts.append({"watchlist_id": wid, "owner_type": ot, "owner_id": ou,
                                   "name": lst["name"], "is_default": i == 0})
            else:
                pw.unchanged += 1
            seen_lists.add(wid)
            _plan_entries(plan, wid, lst["entries"], entries, seen_entries, today)
    pw.orphans = [{"watchlist_id": w["watchlist_id"]} for w in v2.watchlists
                  if (w["owner_type"].upper(), w["owner_id"]) in owners and w["watchlist_id"] not in seen_lists]
    pe.orphans = [{"watchlist_id": k[0], "symbol": k[1]} for k in entries
                  if k[0] in seen_lists and k not in seen_entries]


def _plan_entries(plan: Plan, wid: Any, raw: list, entries: dict, seen: set, today: date) -> None:
    from pi_workers.v1_sync_ledger_plan import diff

    pe = plan["watchlist_entries"]
    for e in raw:
        row, why = map_watch_entry(e)
        if row is None:
            pe.notes[f"skipped_{why}"] += 1
            continue
        k = (wid, row["symbol"])
        if k in seen:
            pe.notes["duplicate_symbol_skipped"] += 1
            continue
        seen.add(k)
        ex = entries.get(k)
        if row["added_date"] is None:  # NOT NULL in v2: keep v2's date, else today
            row["added_date"] = ex["added_date"] if ex else today
            if ex is None:
                pe.notes["added_date_defaulted"] += 1
        row["watchlist_id"] = wid
        if ex is None:
            pe.inserts.append(row)
        elif diff(ex, row, _ENTRY_FIELDS):
            pe.updates.append(row)
        else:
            pe.unchanged += 1


def plan_board(plan: Plan, docs: list[dict], v2: V2Snapshot, new_id: NewId) -> None:
    from pi_workers.v1_sync_ledger_plan import diff

    p = plan["board_items"]
    by_key: dict[tuple, dict] = {}
    for b in v2.board_items:
        by_key.setdefault((str(b["owner_type"]).upper(), b["owner_id"], b["symbol"]), b)
    owners: set[tuple] = set()
    seen: set[tuple] = set()
    for doc in docs:
        ot, ou = owner_uuid(plan, doc.get("owner_type"), doc.get("owner_id"))
        if ou is None:
            plan.reject("board_items", doc, "unknown_owner")
            continue
        owners.add((ot, ou))
        for i, item in enumerate(doc.get("items") or []):
            row, why = map_board_item(item, i)
            if row is None:
                p.notes[f"skipped_{why}"] += 1
                continue
            k = (ot, ou, row["symbol"])
            if k in seen:
                p.notes["duplicate_symbol_skipped"] += 1
                continue
            seen.add(k)
            ex = by_key.get(k)
            row.update(owner_type=ot, owner_id=ou)
            if ex is None:
                p.inserts.append({"item_id": new_id(), **row})
            elif diff(ex, row, _BOARD_FIELDS):
                p.updates.append({"item_id": ex["item_id"], **row})
            else:
                p.unchanged += 1
    p.orphans = [{"item_id": b["item_id"]} for k, b in by_key.items()
                 if (k[0], k[1]) in owners and k not in seen]
