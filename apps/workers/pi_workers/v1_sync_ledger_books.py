"""Planner for the ledger side of the resync: uploads, trades, corporate actions, dividends.

Split out of ``v1_sync_ledger_plan`` (module size limit, AGENTS §3.14). Pure. Trades and
uploads are insert-only (R13.5: append-only ledger); a v1 trade gone from v1 is an orphan,
never deleted. A corporate-action change forces a full recompute (R8).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pi_workers.v1_sync_ledger_map import (
    map_corporate_action,
    map_dividend,
    map_trade,
    map_upload,
)
from pi_workers.v1_sync_ledger_plan import diff

if TYPE_CHECKING:
    from pi_workers.v1_sync_ledger_plan import Plan, V2Snapshot


def plan_uploads(plan: Plan, docs: list[dict], v2: V2Snapshot) -> None:
    p = plan["uploads"]
    legacy = {u["legacy_id"] for u in v2.uploads if u.get("legacy_id")}
    by_hash = {(u["client_id"], bytes(u["file_sha256"])) for u in v2.uploads}
    for doc in docs:
        cu = plan.client_map.get(str(doc.get("client_id")))
        if cu is None:
            plan.reject("uploads", doc, "unknown_client")
            continue
        row, why = map_upload(doc, cu)
        if row is None:
            plan.reject("uploads", doc, why or "invalid")
            continue
        k = (cu, row["file_sha256"])
        if row["legacy_id"] in legacy or k in by_hash:
            p.unchanged += 1  # forced v1 re-uploads share a hash: one v2 row per file
            continue
        by_hash.add(k)
        p.inserts.append(row)


def plan_trades(plan: Plan, docs: list[dict], v2: V2Snapshot) -> None:
    p = plan["trades"]
    idx = {(t["client_id"], t["fingerprint"]): t for t in v2.trades}
    v2_legacy = {t["legacy_id"] for t in v2.trades if t.get("legacy_id")}
    v1_keys: set[tuple] = set()
    for doc in docs:
        cu = plan.client_map.get(str(doc.get("client_id")))
        if cu is not None and doc.get("fingerprint"):
            v1_keys.add((cu, str(doc["fingerprint"]).strip()))
    seen: set[tuple] = set()
    for doc in docs:
        cu = plan.client_map.get(str(doc.get("client_id")))
        if cu is None:
            plan.reject("trades", doc, "unknown_client")
            continue
        row, why = map_trade(doc, cu)
        if row is None:
            plan.reject("trades", doc, why or "invalid")
            continue
        k = (cu, row["fingerprint"])
        if k in seen:
            plan.reject("trades", doc, "duplicate_fingerprint")
            continue
        seen.add(k)
        ex = idx.get(k)
        if ex is not None:
            p.unchanged += 1
            if ex.get("deleted"):
                p.notes["tombstoned_in_v2_kept"] += 1
            continue
        if row["legacy_id"] in v2_legacy:
            row["legacy_id"], p.notes["legacy_id_collision"] = None, p.notes["legacy_id_collision"] + 1
        p.inserts.append(row)
        p.notes[f"new_source_{row['source']}"] += 1
        plan.changed_clients.add(cu)
    v1_clients = set(plan.client_map.values())
    for t in v2.trades:
        k = (t["client_id"], t["fingerprint"])
        if t.get("deleted") or k in v1_keys:
            continue
        if not t.get("v1_origin"):
            p.notes["v2_native_not_in_v1"] += 1
        elif t["client_id"] in v1_clients:
            p.orphans.append({"client_id": t["client_id"], "fingerprint": t["fingerprint"],
                              "symbol": t.get("symbol")})


def plan_corporate_actions(plan: Plan, docs: list[dict], v2: V2Snapshot) -> None:
    p = plan["corporate_actions"]
    by_key = {c["key"]: c for c in v2.corporate_actions}
    fields = ("isin", "symbol", "ex_date", "type", "qty_multiplier", "amount_per_share", "subject", "source")
    seen: set[str] = set()
    for doc in docs:
        row, why = map_corporate_action(doc)
        if row is None:
            plan.reject("corporate_actions", doc, why or "invalid")
            continue
        if row["key"] in seen:
            plan.reject("corporate_actions", doc, "duplicate_key")
            continue
        seen.add(row["key"])
        ex = by_key.get(row["key"])
        if ex is None:
            p.inserts.append(row)
        elif diff(ex, row, fields):
            p.updates.append(row)
        else:
            p.unchanged += 1
    p.orphans = [{"key": k} for k in by_key if k not in seen]
    if p.inserts or p.updates:
        plan.recompute_all = True  # R8: a split/bonus changes quantity for every holder


def plan_dividends(plan: Plan, docs: list[dict], v2: V2Snapshot) -> None:
    p = plan["dividends"]
    by_key: dict[tuple, dict] = {}
    for d in v2.dividends:
        by_key.setdefault((d["client_id"], d["symbol"], d["ex_date"]), d)
    seen: set[tuple] = set()
    for doc in docs:
        cu = plan.client_map.get(str(doc.get("client_id")))
        if cu is None:
            plan.reject("dividends", doc, "unknown_client")
            continue
        row, why = map_dividend(doc, cu)
        if row is None:
            plan.reject("dividends", doc, why or "invalid")
            continue
        k = (cu, row["symbol"], row["ex_date"])
        if k in seen:
            plan.reject("dividends", doc, "duplicate_natural_key")
            continue
        seen.add(k)
        ex = by_key.get(k)
        if ex is None:
            p.inserts.append(row)
        elif diff(ex, row, ("amount_per_share", "quantity", "source")):
            p.updates.append(row)
        else:
            p.unchanged += 1
            continue
        plan.changed_clients.add(cu)
    v1_clients = set(plan.client_map.values())
    p.orphans = [{"client_id": k[0], "symbol": k[1], "ex_date": k[2]}
                 for k in by_key if k not in seen and k[0] in v1_clients]
