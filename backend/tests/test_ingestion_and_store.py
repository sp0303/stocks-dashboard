"""Ingestion against the real tradebooks + store dedupe behavior."""
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ingestion import parse_tradebook
from app.store import JsonStore

TB_Q = "/home/sumanth/Downloads/tradebook-QPJ806-EQ (1).xlsx"
TB_A = "/home/sumanth/Downloads/tradebook-AP8774-EQ.xlsx"
HAVE_FILES = Path(TB_Q).exists() and Path(TB_A).exists()

pytestmark = pytest.mark.skipif(not HAVE_FILES, reason="tradebook files not present")


def test_parse_qpj806():
    p = parse_tradebook(TB_Q)
    assert p.client_id == "QPJ806"
    assert p.date_from == "2026-01-01"
    assert len(p.trades) == 53
    assert p.errors == []
    assert all(t["trade_type"] in ("buy", "sell") for t in p.trades)
    assert all(t["fingerprint"] for t in p.trades)


def test_parse_ap8774():
    p = parse_tradebook(TB_A)
    assert p.client_id == "AP8774"
    assert len(p.trades) == 585
    assert p.errors == []


def test_fingerprints_unique_within_file():
    p = parse_tradebook(TB_A)
    fps = [t["fingerprint"] for t in p.trades]
    # each Zerodha row has a distinct Trade ID -> distinct fingerprint
    assert len(set(fps)) == len(fps)


@pytest.mark.asyncio
async def test_store_dedupe_on_reimport():
    with tempfile.TemporaryDirectory() as d:
        store = JsonStore(d)
        await store.init()
        p = parse_tradebook(TB_Q)
        for t in p.trades:
            t["client_id"] = "cid1"
        ins1, dup1 = await store.insert_trades([dict(t) for t in p.trades])
        assert ins1 == 53 and dup1 == 0
        # re-insert same trades -> all duplicates, none doubled
        ins2, dup2 = await store.insert_trades([dict(t) for t in p.trades])
        assert ins2 == 0 and dup2 == 53
        assert await store.count_trades("cid1") == 53
