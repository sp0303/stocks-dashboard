"""Multi-list watchlist behaviour on the JSON store.

These exercise the store layer directly (no external fixtures, so they always run):
legacy single-list migration, per-list isolation, rename/delete, and the
default-list resolution that keeps single-list callers (clients, alert sweep)
working when no watchlist_id is passed.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.store import JsonStore


async def _store():
    d = tempfile.mkdtemp()
    s = JsonStore(d)
    await s.init()
    return s


async def test_default_list_created_and_add_without_id():
    s = await _store()
    # no watchlist_id -> operates on (and creates) the owner's default list
    await s.add_watchlist_symbol("CLIENT", "c1", "INFY", added_price=100)
    entries = await s.get_watchlist("CLIENT", "c1")
    assert [e["symbol"] for e in entries] == ["INFY"]
    lists = await s.list_watchlists("CLIENT", "c1")
    assert len(lists) == 1 and lists[0]["count"] == 1


async def test_legacy_single_list_doc_migrates():
    s = await _store()
    # simulate a pre-existing legacy doc (bare "entries", no "lists")
    s._db["watchlists"].append({
        "owner_type": "MANAGER", "owner_id": "m1",
        "entries": [{"symbol": "TCS", "added_date": "2025-01-01", "added_price": 3500}],
    })
    lists = await s.list_watchlists("MANAGER", "m1")
    assert len(lists) == 1
    assert lists[0]["id"] == "default" and lists[0]["name"] == "Watchlist 1"
    assert lists[0]["count"] == 1
    # the migrated entry is readable via the default list
    assert [e["symbol"] for e in await s.get_watchlist("MANAGER", "m1")] == ["TCS"]


async def test_multiple_lists_are_isolated():
    s = await _store()
    await s.add_watchlist_symbol("MANAGER", "m1", "INFY")  # default list
    b = await s.create_watchlist("MANAGER", "m1", "Momentum")
    await s.add_watchlist_symbol("MANAGER", "m1", "TCS", watchlist_id=b["id"])

    default_syms = [e["symbol"] for e in await s.get_watchlist("MANAGER", "m1")]
    momentum_syms = [e["symbol"] for e in await s.get_watchlist("MANAGER", "m1", b["id"])]
    assert default_syms == ["INFY"]
    assert momentum_syms == ["TCS"]

    # get_watchlists (used by the alert sweep) returns every list with its entries
    all_lists = await s.get_watchlists("MANAGER", "m1")
    assert {l["name"] for l in all_lists} == {"Watchlist 1", "Momentum"}
    assert sum(len(l["entries"]) for l in all_lists) == 2


async def test_rename_and_delete_watchlist():
    s = await _store()
    await s.add_watchlist_symbol("MANAGER", "m1", "INFY")
    b = await s.create_watchlist("MANAGER", "m1", "Swing")

    renamed = await s.rename_watchlist("MANAGER", "m1", b["id"], "Positional")
    assert renamed["name"] == "Positional"

    assert await s.delete_watchlist("MANAGER", "m1", b["id"]) is True
    names = [l["name"] for l in await s.list_watchlists("MANAGER", "m1")]
    assert names == ["Watchlist 1"]
    # deleting a non-existent list is a no-op that reports False
    assert await s.delete_watchlist("MANAGER", "m1", "nope") is False


async def test_update_and_remove_target_the_right_list():
    s = await _store()
    a = await s.create_watchlist("MANAGER", "m1", "A")
    b = await s.create_watchlist("MANAGER", "m1", "B")
    await s.add_watchlist_symbol("MANAGER", "m1", "INFY", watchlist_id=a["id"])
    await s.add_watchlist_symbol("MANAGER", "m1", "INFY", watchlist_id=b["id"])

    # editing INFY in list A must not touch INFY in list B
    await s.update_watchlist_entry("MANAGER", "m1", "INFY", {"alert_price": 1500}, watchlist_id=a["id"])
    a_entry = (await s.get_watchlist("MANAGER", "m1", a["id"]))[0]
    b_entry = (await s.get_watchlist("MANAGER", "m1", b["id"]))[0]
    assert a_entry["alert_price"] == 1500
    assert b_entry["alert_price"] is None

    await s.remove_watchlist_symbol("MANAGER", "m1", "INFY", watchlist_id=a["id"])
    assert await s.get_watchlist("MANAGER", "m1", a["id"]) == []
    assert [e["symbol"] for e in await s.get_watchlist("MANAGER", "m1", b["id"])] == ["INFY"]


async def test_persists_across_reload():
    with tempfile.TemporaryDirectory() as d:
        s = JsonStore(d)
        await s.init()
        b = await s.create_watchlist("MANAGER", "m1", "Momentum")
        await s.add_watchlist_symbol("MANAGER", "m1", "TCS", watchlist_id=b["id"])

        # a fresh store reading the same file sees the lists
        s2 = JsonStore(d)
        await s2.init()
        lists = await s2.list_watchlists("MANAGER", "m1")
        names = {l["name"] for l in lists}
        assert "Momentum" in names
        moved = next(l for l in lists if l["name"] == "Momentum")
        assert [e["symbol"] for e in await s2.get_watchlist("MANAGER", "m1", moved["id"])] == ["TCS"]
