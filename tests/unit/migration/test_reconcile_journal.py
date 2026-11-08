"""Fingerprint resolution + fallback for the v1 trade-journal reconcile script."""

from datetime import date
from decimal import Decimal

from reconcile_trade_notes_tags import (
    V2Index,
    build_client_map,
    extract_journal,
    resolve,
    trade_key,
    v1_trade_key_map,
)

C1 = "11111111-1111-1111-1111-111111111111"


def _v2(
    trade_id, fp, qty="10", price="100.5", sym="INFY", d=date(2025, 1, 2), side="buy"
):
    return {
        "trade_id": trade_id,
        "client_id": C1,
        "fingerprint": fp,
        "symbol": sym,
        "trade_date": d,
        "trade_type": side,
        "quantity": Decimal(qty),
        "price": Decimal(price),
    }


def test_extract_splits_notes_and_tags_and_counts_dangling():
    tt = [
        {
            "_id": "a",
            "client_id": "c1",
            "fingerprint": "fp1",
            "tag_ids": ["t1", "gone"],
            "note": " why ",
        },
        {
            "_id": "b",
            "client_id": "c1",
            "fingerprint": "fp2",
            "tag_ids": [],
            "note": "",
        },
    ]
    notes = [
        {"_id": "n1", "client_id": "c1", "fingerprint": "fp1", "note": "dupe"},
        {"_id": "n2", "client_id": "c1", "fingerprint": "fp3", "text": "other"},
        {"_id": "n3", "client_id": "c1", "fingerprint": "fp4", "note": ""},
    ]
    ex = extract_journal(tt, notes, [{"id": "t1", "name": "Breakout", "color": "#000"}])
    assert [n.v1_id for n in ex.notes] == ["a", "n2"]
    assert ex.notes[0].note == "why"
    assert [t.tag_name for t in ex.tags] == ["Breakout"]
    assert ex.counts["dangling_tag_refs"] == 1
    assert ex.counts["note_dupe_of_trade_tags"] == 1
    assert ex.counts["empty_notes"] == 1
    assert ex.counts["expected_notes"] == 2 and ex.counts["expected_tag_links"] == 1


def test_client_map_matches_id_or_objectid():
    cmap = build_client_map([{"_id": "oid1", "id": "c1"}], [(C1, "oid1")])
    assert cmap["c1"] == C1 and cmap["oid1"] == C1


def test_resolve_exact_fingerprint():
    idx = V2Index.build([_v2(7, "fp1")])
    assert resolve("c1", "fp1", None, {"c1": C1}, {}, idx) == (C1, 7, "exact")


def test_resolve_fallback_via_v1_trade_when_fingerprint_drifted():
    idx = V2Index.build([_v2(7, "new-fp")])
    v1 = v1_trade_key_map(
        [
            {
                "client_id": "c1",
                "fingerprint": "old-fp",
                "symbol": "infy ",
                "trade_date": "2025-01-02T00:00:00",
                "trade_type": "BUY",
                "quantity": 10,
                "price": 100.50,
            }
        ]
    )
    assert resolve("c1", "old-fp", None, {"c1": C1}, v1, idx) == (C1, 7, "fallback")


def test_resolve_fallback_refuses_ambiguous_match():
    idx = V2Index.build([_v2(7, "x"), _v2(8, "y")])
    hint = trade_key("INFY", "2025-01-02", "buy", 10, "100.5")
    assert resolve("c1", "missing", hint, {"c1": C1}, {}, idx)[1:] == (
        None,
        "ambiguous",
    )


def test_resolve_reports_orphan_no_client_and_no_match():
    idx = V2Index.build([_v2(7, "fp1")])
    assert resolve("cX", "fp1", None, {"c1": C1}, {}, idx)[2] == "no_client"
    assert resolve("c1", "gone", None, {"c1": C1}, {}, idx)[2] == "orphan"
    hint = trade_key("TCS", "2025-01-02", "buy", 10, "100.5")
    assert resolve("c1", "gone", hint, {"c1": C1}, {}, idx)[2] == "no_match"


def test_trade_key_scales_match_numeric_columns():
    assert trade_key("a", "2025-01-02", "Sell", "1.0", 2) == (
        "A",
        "2025-01-02",
        "sell",
        Decimal("1.000000"),
        Decimal("2.0000"),
    )
    assert trade_key(None, "2025-01-02", "buy", 1, 1) is None
    assert trade_key("A", "2025-01-02", "buy", "x", 1) is None
