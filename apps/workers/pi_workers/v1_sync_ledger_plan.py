"""Pure planner for the v1 -> v2 ledger resync: (v1 docs, v2 snapshot) -> Plan.

No I/O. The plan lists every row to insert or update (with v2 keys already resolved, new
UUIDs pre-generated so children of new clients can be planned in a dry run), every
rejected v1 document with its reason (R13.3), and every orphan (a v2 row whose v1 source
is gone). Applying a plan and planning again yields an empty plan (idempotency).

Policy: v1 is the system of record until cutover, so a changed v1 value updates v2 --
except the ledger, which is append-only (R13.5): trades and uploads are insert-only and a
v1-deleted trade only ever becomes a tombstone (``deleted_at``), and only on request.
Ledger entities are planned in ``v1_sync_ledger_books``; research ones (watchlists, board,
theses) in ``v1_sync_ledger_research``.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pi_workers.v1_sync_ledger_map import legacy_id, map_client, map_manager

ENTITIES = (
    "managers", "clients", "uploads", "trades", "corporate_actions", "dividends",
    "stock_theses", "watchlists", "watchlist_entries", "board_items",
)
NewId = Callable[[], uuid.UUID]


@dataclass
class V1Data:
    managers: list[dict] = field(default_factory=list)
    clients: list[dict] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    uploads: list[dict] = field(default_factory=list)
    corporate_actions: list[dict] = field(default_factory=list)
    dividends: list[dict] = field(default_factory=list)
    theses: list[dict] = field(default_factory=list)
    watchlists: list[dict] = field(default_factory=list)
    boards: list[dict] = field(default_factory=list)


@dataclass
class V2Snapshot:
    managers: list[dict] = field(default_factory=list)
    clients: list[dict] = field(default_factory=list)   # + active_trades
    trades: list[dict] = field(default_factory=list)    # client_id, fingerprint, legacy_id, deleted, v1_origin
    uploads: list[dict] = field(default_factory=list)
    corporate_actions: list[dict] = field(default_factory=list)
    dividends: list[dict] = field(default_factory=list)
    theses: list[dict] = field(default_factory=list)
    watchlists: list[dict] = field(default_factory=list)
    watchlist_entries: list[dict] = field(default_factory=list)
    board_items: list[dict] = field(default_factory=list)
    reject_keys: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class Reject:
    entity: str
    v1_id: str
    reason: str
    raw: Any

    @property
    def key(self) -> str:
        return f"{self.entity}:{self.v1_id}"


@dataclass
class EntityPlan:
    inserts: list[dict] = field(default_factory=list)
    updates: list[dict] = field(default_factory=list)
    unchanged: int = 0
    orphans: list[dict] = field(default_factory=list)
    notes: Counter = field(default_factory=Counter)


@dataclass
class Plan:
    entities: dict[str, EntityPlan] = field(default_factory=lambda: {e: EntityPlan() for e in ENTITIES})
    rejects: list[Reject] = field(default_factory=list)
    new_rejects: list[Reject] = field(default_factory=list)
    changed_clients: set = field(default_factory=set)
    recompute_all: bool = False
    flag_trades: list[dict] = field(default_factory=list)
    flag_clients: list[Any] = field(default_factory=list)
    flag_managers: list[Any] = field(default_factory=list)
    client_map: dict[str, Any] = field(default_factory=dict)
    manager_map: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, entity: str) -> EntityPlan:
        return self.entities[entity]

    def reject(self, entity: str, doc: dict, reason: str) -> None:
        self.rejects.append(Reject(entity, legacy_id(doc) or "?", reason, doc))

    @property
    def has_writes(self) -> bool:
        return bool(self.new_rejects) or any(p.inserts or p.updates for p in self.entities.values())

    def counts(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for name, p in self.entities.items():
            out[name] = {"insert": len(p.inserts), "update": len(p.updates),
                         "unchanged": p.unchanged, "orphan": len(p.orphans), **dict(p.notes)}
        out["rejects"] = dict(Counter(f"{r.entity}:{r.reason}" for r in self.rejects))
        out["rejects"]["new"] = len(self.new_rejects)
        return out


def diff(existing: dict, row: dict, fields: tuple[str, ...]) -> bool:
    return any(_norm(existing.get(f)) != _norm(row.get(f)) for f in fields)


def _norm(v: Any) -> Any:
    return v.lower() if isinstance(v, str) and "@" in v else v


# ── core ──────────────────────────────────────────────────────────────────────

_MGR_FIELDS = ("legacy_id", "name", "firm", "email", "is_active")
_CLIENT_FIELDS = ("legacy_id", "manager_id", "name", "client_code", "broker", "status")


def plan_managers(plan: Plan, docs: list[dict], v2: V2Snapshot, new_id: NewId) -> None:
    p = plan["managers"]
    by_legacy = {m["legacy_id"]: m for m in v2.managers if m.get("legacy_id")}
    by_email = {str(m["email"]).lower(): m for m in v2.managers}
    seen_email: set[str] = set()
    for doc in docs:
        row, why = map_manager(doc)
        if row is None:
            plan.reject("managers", doc, why or "invalid")
            continue
        email = row["email"].lower()
        if email in seen_email:
            plan.reject("managers", doc, "duplicate_email")
            continue
        seen_email.add(email)
        ex = by_legacy.get(row["legacy_id"])
        if ex is None:
            cand = by_email.get(email)
            ex = cand if cand and not cand.get("legacy_id") else None
            if cand and ex is None:
                plan.reject("managers", doc, "email_taken_by_other_manager")
                continue
        if ex is None:
            p.inserts.append({"manager_id": new_id(), **row})
            plan.manager_map[row["legacy_id"]] = p.inserts[-1]["manager_id"]
            continue
        plan.manager_map[row["legacy_id"]] = ex["manager_id"]
        if diff(ex, row, _MGR_FIELDS):
            p.updates.append({"manager_id": ex["manager_id"], **row})
        else:
            p.unchanged += 1
    matched = set(plan.manager_map.values())
    p.orphans = [{"manager_id": m["manager_id"]} for m in v2.managers
                 if m["manager_id"] not in matched and m.get("is_active", True)]


def plan_clients(plan: Plan, docs: list[dict], v2: V2Snapshot, new_id: NewId) -> None:
    p = plan["clients"]
    by_legacy = {c["legacy_id"]: c for c in v2.clients if c.get("legacy_id")}
    by_code = {(c["manager_id"], str(c["client_code"]).upper()): c
               for c in v2.clients if c.get("client_code")}
    for doc in docs:
        row, why = map_client(doc)
        if row is None:
            plan.reject("clients", doc, why or "invalid")
            continue
        mid = plan.manager_map.get(row.pop("v1_manager_id"))
        if mid is None:
            plan.reject("clients", doc, "unknown_manager")
            continue
        row["manager_id"] = mid
        code_key = (mid, (row["client_code"] or "").upper())
        ex = by_legacy.get(row["legacy_id"])
        holder = by_code.get(code_key) if row["client_code"] else None
        if ex is None and holder is not None and not holder.get("legacy_id"):
            ex = holder
        if holder is not None and ex is not None and holder["client_id"] != ex["client_id"]:
            plan.reject("clients", doc, "client_code_taken")
            continue
        if ex is None and holder is not None:
            plan.reject("clients", doc, "client_code_taken")
            continue
        if ex is None:
            cid = new_id()
            p.inserts.append({"client_id": cid, **row})
            plan.client_map[row["legacy_id"]] = cid
            plan.changed_clients.add(cid)
            if row["client_code"]:
                by_code[code_key] = p.inserts[-1]
            continue
        plan.client_map[row["legacy_id"]] = ex["client_id"]
        if row["broker"] is None:
            row["broker"] = ex.get("broker")  # v1 rarely records a broker: keep v2's
        if diff(ex, row, _CLIENT_FIELDS):
            p.updates.append({"client_id": ex["client_id"], **row})
            plan.changed_clients.add(ex["client_id"])
        else:
            p.unchanged += 1
    matched = set(plan.client_map.values())
    p.orphans = [
        {"client_id": c["client_id"], "client_code": c.get("client_code"),
         "active_trades": int(c.get("active_trades") or 0)}
        for c in v2.clients if c["client_id"] not in matched and c.get("status") != "INACTIVE"
    ]


def plan_orphan_flags(plan: Plan, v2: V2Snapshot) -> None:
    """What --flag-orphans would soft-flag. Never a hard delete."""
    plan.flag_trades = list(plan["trades"].orphans)
    plan.flag_clients = [o["client_id"] for o in plan["clients"].orphans if o["active_trades"] == 0]
    flagged = set(plan.flag_clients)
    live = {c["manager_id"] for c in v2.clients
            if c.get("status") != "INACTIVE" and c["client_id"] not in flagged}
    live |= {c["manager_id"] for c in plan["clients"].inserts}
    plan.flag_managers = [o["manager_id"] for o in plan["managers"].orphans if o["manager_id"] not in live]


def finalize(plan: Plan, v2: V2Snapshot) -> None:
    plan.new_rejects = [r for r in plan.rejects if r.key not in v2.reject_keys]
    plan_orphan_flags(plan, v2)


def plan_sync(v1: V1Data, v2: V2Snapshot, today: date, new_id: NewId = uuid.uuid4) -> Plan:
    from pi_workers.v1_sync_ledger_books import (
        plan_corporate_actions,
        plan_dividends,
        plan_trades,
        plan_uploads,
    )
    from pi_workers.v1_sync_ledger_research import (
        plan_board,
        plan_theses,
        plan_watchlists,
    )

    plan = Plan()
    plan_managers(plan, v1.managers, v2, new_id)
    plan_clients(plan, v1.clients, v2, new_id)
    plan_uploads(plan, v1.uploads, v2)
    plan_trades(plan, v1.trades, v2)
    plan_corporate_actions(plan, v1.corporate_actions, v2)
    plan_dividends(plan, v1.dividends, v2)
    plan_theses(plan, v1.theses, v2)
    plan_watchlists(plan, v1.watchlists, v2, today, new_id)
    plan_board(plan, v1.boards, v2, new_id)
    finalize(plan, v2)
    return plan
