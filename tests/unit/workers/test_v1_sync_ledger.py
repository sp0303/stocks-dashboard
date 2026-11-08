"""v1 -> v2 ledger resync: mapping, planning, idempotency, orphans (R8, R9, R13, R15)."""

import json
import uuid
from datetime import date
from decimal import Decimal
from itertools import count

import pytest
from pi_workers.v1_sync_ledger_map import (
    map_client,
    map_corporate_action,
    map_dividend,
    map_manager,
    map_trade,
    map_upload,
)
from pi_workers.v1_sync_ledger_plan import V1Data, V2Snapshot, plan_sync
from pi_workers.v1_sync_ledger_research import (
    map_board_item,
    map_thesis,
    map_watch_entry,
    watchlist_lists,
)

TODAY = date(2026, 11, 8)
CID = uuid.UUID(int=1)


def ids():
    n = count(1000)
    return lambda: uuid.UUID(int=next(n))


def trade(fp, **kw):
    d = {"id": f"t{fp}", "client_id": "c1", "fingerprint": fp, "symbol": "infy", "isin": "INE009A01021",
         "trade_date": "2026-10-20", "exchange": "NSE", "segment": "EQ", "series": "EQ",
         "trade_type": "buy", "auction": False, "quantity": 10.0, "price": 1500.5,
         "trade_id": f"T{fp}", "order_id": f"O{fp}", "order_execution_time": "2026-10-20 10:01:02",
         "charges": 0.0}
    d.update(kw)
    return d


def v1_book(**over):
    base = {
        "managers": [{"id": "m1", "name": "SP", "email": "sp@example.test", "status": "ACTIVE"}],
        "clients": [{"id": "c1", "name": "Client One", "portfolio_manager_id": "m1", "client_code": "AB1234"}],
        "trades": [trade("f1"), trade("f2", trade_type="sell", quantity=4.0)],
        "uploads": [{"id": "u1", "client_id": "c1", "version": 1, "file_name": "tb.xlsx", "file_hash": "ab" * 32,
                  "row_count": 2, "imported_count": 2, "duplicate_count": 0, "error_count": 0}],
        "corporate_actions": [{"key": "INE009A01021|2026-11-04|BONUS|Bonus 1:1", "isin": "INE009A01021",
                            "symbol": "INFY", "ex_date": "2026-11-04", "type": "BONUS", "qty_multiplier": 2.0}],
        "dividends": [{"id": "d1", "client_id": "c1", "symbol": "infy", "ex_date": "2026-10-25",
                    "amount_per_share": 20, "quantity": 6, "source": "manual"}],
        "theses": [{"_id": "x", "client_id": "c1", "symbol": "INFY", "why": "moat"}],
        "watchlists": [{"owner_type": "MANAGER", "owner_id": "m1",
                     "lists": [{"id": "l1", "name": "Core", "entries": [{"symbol": "tcs", "why": "IT"}]}]}],
        "boards": [{"owner_type": "MANAGER", "owner_id": "m1",
                 "items": [{"id": "b1", "symbol": "hdfcbank", "status": "entered", "entry_price": 1600}]}],
    }
    base.update(over)
    return V1Data(**base)


def apply_to_snapshot(plan, snap: V2Snapshot) -> V2Snapshot:
    """In-memory stand-in for PgLedgerRepo.apply (MERGE semantics per entity key)."""
    def upsert(rows, new, key):
        by = {key(r): r for r in rows}
        for r in new:
            by.setdefault(key(r), {}).update(r)
        return list(by.values())

    e = plan.entities
    snap.managers = upsert(snap.managers, e["managers"].inserts + e["managers"].updates, lambda r: r["manager_id"])
    snap.clients = upsert(snap.clients, e["clients"].inserts + e["clients"].updates, lambda r: r["client_id"])
    snap.uploads += e["uploads"].inserts
    snap.trades += [{**t, "deleted": False, "v1_origin": True} for t in e["trades"].inserts]
    for t in plan.flag_trades:
        for s in snap.trades:
            if (s["client_id"], s["fingerprint"]) == (t["client_id"], t["fingerprint"]):
                s["deleted"] = True
    for c in snap.clients:
        if c["client_id"] in plan.flag_clients:
            c["status"] = "INACTIVE"
    snap.corporate_actions = upsert(snap.corporate_actions, e["corporate_actions"].inserts
                                    + e["corporate_actions"].updates, lambda r: r["key"])
    snap.dividends = upsert(snap.dividends, e["dividends"].inserts + e["dividends"].updates,
                            lambda r: (r["client_id"], r["symbol"], r["ex_date"]))
    snap.theses = upsert(snap.theses, e["stock_theses"].inserts + e["stock_theses"].updates,
                         lambda r: (r["client_id"], r["symbol"]))
    snap.watchlists += e["watchlists"].inserts
    snap.watchlist_entries = upsert(snap.watchlist_entries, e["watchlist_entries"].inserts
                                    + e["watchlist_entries"].updates, lambda r: (r["watchlist_id"], r["symbol"]))
    snap.board_items = upsert(snap.board_items, e["board_items"].inserts + e["board_items"].updates,
                              lambda r: r["item_id"])
    snap.reject_keys |= {r.key for r in plan.new_rejects}
    return snap


def writes(plan):
    return {k: (len(p.inserts), len(p.updates)) for k, p in plan.entities.items() if p.inserts or p.updates}


# ── mapping ─────────────────────────────────────────────────────────────────


def test_map_trade_keeps_fingerprint_broker_ids_and_raw():
    row, why = map_trade(trade("f1"), CID)
    assert why is None
    assert row["fingerprint"] == "f1" and row["broker_trade_id"] == "Tf1" and row["broker_order_id"] == "Of1"
    assert row["symbol"] == "INFY" and row["quantity"] == Decimal(10) and row["price"] == Decimal("1500.5")
    assert row["source"] == "upload" and row["segment"] == "EQ"
    assert row["executed_at"].utcoffset().total_seconds() == 19800  # naive v1 time is IST
    raw = json.loads(row["extra"])["v1"]
    assert raw["order_id"] == "Of1" and raw["charges"] == 0.0  # lossless (R13.2)


def test_map_trade_charges_placeholder_is_null_not_zero():  # R15
    row, _ = map_trade(trade("f1"), CID)
    assert row["charges"] is None and row["charges_known"] is False


def test_manual_trade_source_and_note_preserved_zero_price_allowed():
    doc = trade("m1", source="manual", note="IPO allotment HDBFS@740", trade_id="", order_id="",
                price=0, order_execution_time="2026-10-24T00:00:00")
    row, why = map_trade(doc, CID)
    assert why is None and row["source"] == "manual" and row["note"].startswith("IPO")
    assert row["broker_trade_id"] is None and row["price"] == 0
    assert map_trade({**doc, "source": None}, CID) == (None, "bad_price")  # only manual may be 0


def test_groww_row_maps():
    doc = trade("g1", trade_id="GRW123", order_id="GRW123", segment="", exchange="BSE", price=412.3333,
                order_execution_time="2026-10-15 09:31:00")
    row, why = map_trade(doc, CID)
    assert why is None and row["exchange"] == "BSE" and row["segment"] == "EQ"
    assert row["broker_trade_id"] == row["broker_order_id"] == "GRW123"
    assert row["price"] == Decimal("412.3333")


@pytest.mark.parametrize("over,reason", [
    ({"fingerprint": ""}, "missing_fingerprint"),
    ({"trade_date": "20/13/2026x"}, "bad_trade_date"),
    ({"trade_type": "hold"}, "bad_trade_type"),
    ({"quantity": 0}, "bad_quantity"),
    ({"exchange": "NFO"}, "unsupported_exchange:NFO"),
])
def test_map_trade_rejects_with_reason(over, reason):
    assert map_trade(trade("f", **over), CID) == (None, reason)


def test_map_trade_blank_exchange_defaults_to_nse_and_says_so():
    row, _ = map_trade(trade("f", exchange=""), CID)
    assert row["exchange"] == "NSE" and json.loads(row["extra"])["exchange_defaulted"] is True


def test_map_core_entities():
    m, _ = map_manager({"id": "m1", "name": "SP", "email": "sp@x.test", "status": "INACTIVE"})
    assert m["is_active"] is False
    assert map_manager({"id": "m2", "name": "No mail"}) == (None, "missing_email")
    c, _ = map_client({"id": "c9", "name": "Groww Demo", "portfolio_manager_id": "m1",
                       "client_code": "Grow account", "broker": "groww"})
    assert c["broker"] == "OTHER" and c["client_code"] == "Grow account" and c["status"] == "ACTIVE"


def test_map_ledger_side_entities():
    u, _ = map_upload({"id": "u", "file_hash": "00" * 32, "row_count": 5, "error_count": 2,
                       "imported_count": 3, "duplicate_count": 2, "status": "PARTIAL"}, CID)
    assert u["rows_total"] == 7 and u["rows_rejected"] == 2 and len(u["file_sha256"]) == 32
    ca, _ = map_corporate_action({"key": "k", "symbol": "irctc", "ex_date": "2021-10-28", "type": "split",
                                  "qty_multiplier": 5})
    assert ca["type"] == "SPLIT" and ca["qty_multiplier"] == Decimal(5) and ca["source"] == "NSE"
    assert map_corporate_action({"key": "k", "symbol": "x", "ex_date": "x"}) == (None, "bad_ex_date")
    d, _ = map_dividend({"symbol": "itc", "ex_date": "2026-06-01", "amount_per_share": "6.5",
                         "quantity": 100, "source": "nse_auto"}, CID)
    assert d["source"] == "nse" and d["amount_per_share"] == Decimal("6.5")
    t, _ = map_thesis({"_id": 1, "client_id": "c1", "symbol": "itc", "why": "cash"}, CID)
    assert t["thesis"] == {"why": "cash"}


def test_map_research_entities():
    assert watchlist_lists({"symbols": ["A", "B"]})[0]["entries"] == [{"symbol": "A"}, {"symbol": "B"}]
    e, _ = map_watch_entry({"symbol": "tcs", "checkpoint_date": "2026-01-02", "added_price": "3500"})
    assert e["added_date"] == date(2026, 1, 2) and e["symbol"] == "TCS"
    b, _ = map_board_item({"symbol": "x", "status": "exited"}, 3)
    assert b["lane"] == "exit" and b["sort_order"] == 3


# ── planning ─────────────────────────────────────────────────────────────────


def test_empty_v2_gets_everything_including_missing_clients_and_manager():
    plan = plan_sync(v1_book(), V2Snapshot(), TODAY, ids())
    assert writes(plan) == {
        "managers": (1, 0), "clients": (1, 0), "uploads": (1, 0), "trades": (2, 0),
        "corporate_actions": (1, 0), "dividends": (1, 0), "stock_theses": (1, 0),
        "watchlists": (1, 0), "watchlist_entries": (1, 0), "board_items": (1, 0),
    }
    cid = plan["clients"].inserts[0]["client_id"]
    assert plan["clients"].inserts[0]["manager_id"] == plan["managers"].inserts[0]["manager_id"]
    assert {t["client_id"] for t in plan["trades"].inserts} == {cid}  # children use the new id
    assert plan["board_items"].inserts[0]["lane"] == "holding"
    assert plan["watchlist_entries"].inserts[0]["added_date"] == TODAY  # NOT NULL in v2
    assert plan.recompute_all and cid in plan.changed_clients


def test_second_run_is_a_no_op():
    v1 = v1_book(trades=[trade("f1"), trade("bad", quantity=-1)])
    snap = apply_to_snapshot(plan_sync(v1, V2Snapshot(), TODAY, ids()), V2Snapshot())
    again = plan_sync(v1, snap, TODAY, ids())
    assert writes(again) == {} and not again.has_writes
    assert again["trades"].unchanged == 1 and again.new_rejects == []  # reject stored once
    assert not again.changed_clients and not again.recompute_all


def test_fingerprint_dedupe_within_v1_and_against_v2():
    v1 = v1_book(trades=[trade("f1"), trade("f1", id="dup")])
    plan = plan_sync(v1, V2Snapshot(), TODAY, ids())
    assert len(plan["trades"].inserts) == 1
    assert [r.reason for r in plan.rejects] == ["duplicate_fingerprint"]


def existing_v2():
    """v2 as the 2026-10-04 migration left it: manager, client (by legacy id), one trade."""
    mid, cid = uuid.UUID(int=10), uuid.UUID(int=20)
    return V2Snapshot(
        managers=[{"manager_id": mid, "legacy_id": "m1", "name": "SP", "firm": None,
                   "email": "SP@example.test", "is_active": True}],
        clients=[{"client_id": cid, "legacy_id": "c1", "manager_id": mid, "name": "Client One",
                  "client_code": "AB1234", "broker": "ZERODHA", "status": "ACTIVE", "active_trades": 2},
                 {"client_id": uuid.UUID(int=99), "legacy_id": None, "manager_id": mid, "name": "test",
                  "client_code": None, "broker": None, "status": "ACTIVE", "active_trades": 0}],
        trades=[{"client_id": cid, "fingerprint": "f1", "legacy_id": "tf1", "symbol": "INFY",
                 "deleted": False, "v1_origin": True},
                {"client_id": cid, "fingerprint": "gone", "legacy_id": "tgone", "symbol": "TCS",
                 "deleted": False, "v1_origin": True},
                {"client_id": cid, "fingerprint": "v2own", "legacy_id": None, "symbol": "ITC",
                 "deleted": False, "v1_origin": False}],
    ), mid, cid


def test_incremental_against_migrated_v2_and_v2_broker_kept():
    snap, _mid, _cid = existing_v2()
    plan = plan_sync(v1_book(), snap, TODAY, ids())
    assert plan["managers"].unchanged == 1  # email compared case-insensitively
    assert plan["clients"].unchanged == 1   # v1 has no broker: v2's ZERODHA kept, no update
    assert [t["fingerprint"] for t in plan["trades"].inserts] == ["f2"]
    assert plan["trades"].unchanged == 1


def test_orphans_reported_and_flag_candidates_are_safe():
    snap, _mid, _cid = existing_v2()
    plan = plan_sync(v1_book(), snap, TODAY, ids())
    assert [o["fingerprint"] for o in plan["trades"].orphans] == ["gone"]  # v2-native trade never orphaned
    assert plan["trades"].notes["v2_native_not_in_v1"] == 1
    assert [o["client_id"] for o in plan["clients"].orphans] == [uuid.UUID(int=99)]
    assert plan.flag_clients == [uuid.UUID(int=99)]  # empty junk client
    assert plan.flag_managers == []                  # manager still has a live client


def test_orphan_client_with_trades_is_not_flagged():
    snap, _, _ = existing_v2()
    snap.clients[1]["active_trades"] = 3
    plan = plan_sync(v1_book(), snap, TODAY, ids())
    assert plan["clients"].orphans and plan.flag_clients == []


def test_flag_then_replan_is_stable():
    snap, _, _ = existing_v2()
    plan = plan_sync(v1_book(), snap, TODAY, ids())
    snap = apply_to_snapshot(plan, snap)
    again = plan_sync(v1_book(), snap, TODAY, ids())
    assert again.flag_trades == [] and again.flag_clients == [] and not again.has_writes


def test_tombstoned_trade_not_reinserted():
    snap, _, _cid = existing_v2()
    snap.trades[0]["deleted"] = True
    plan = plan_sync(v1_book(), snap, TODAY, ids())
    assert "f1" not in [t["fingerprint"] for t in plan["trades"].inserts]
    assert plan["trades"].notes["tombstoned_in_v2_kept"] == 1


def test_changed_v1_values_update_v2_but_trades_stay_append_only():
    v1 = v1_book()
    snap = apply_to_snapshot(plan_sync(v1, V2Snapshot(), TODAY, ids()), V2Snapshot())
    v1.dividends[0]["quantity"] = 7
    v1.corporate_actions[0]["qty_multiplier"] = 3
    v1.clients[0]["name"] = "Client One Renamed"
    v1.trades[0]["note"] = "edited"
    plan = plan_sync(v1, snap, TODAY, ids())
    assert writes(plan) == {"dividends": (0, 1), "corporate_actions": (0, 1), "clients": (0, 1)}


def test_unknown_client_and_owner_are_rejected_with_reason():
    v1 = v1_book(trades=[trade("f1", client_id="nope")],
                 boards=[{"owner_type": "CLIENT", "owner_id": "nope", "items": []}])
    plan = plan_sync(v1, V2Snapshot(), TODAY, ids())
    assert {(r.entity, r.reason) for r in plan.rejects} == {("trades", "unknown_client"),
                                                             ("board_items", "unknown_owner")}


def test_manager_email_owned_by_other_legacy_manager_rejected():
    snap = V2Snapshot(managers=[{"manager_id": uuid.UUID(int=5), "legacy_id": "other", "name": "X",
                                 "firm": None, "email": "sp@example.test", "is_active": True}])
    plan = plan_sync(v1_book(), snap, TODAY, ids())
    assert ("managers", "email_taken_by_other_manager") in {(r.entity, r.reason) for r in plan.rejects}
    assert plan["clients"].inserts == []  # its client cannot be placed either
