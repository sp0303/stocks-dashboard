"""Service tests: manual trade idempotency, recompute isolation, side normalisation."""

import asyncio
import uuid
from datetime import date

from pi_api.modules.ledger.service import LedgerService


class FakeRepo:
    def __init__(self):
        self.fps = {}
        self.calls = []

    async def insert_manual_trade(self, conn, fp, t):
        if fp in self.fps:
            return None
        self.fps[fp] = t
        return len(self.fps)

    async def list_trades(self, *args):
        self.calls.append(args)
        return []


def _trade(**kw):
    base = {
        "client_id": uuid.uuid4(),
        "symbol": " infy ",
        "exchange": "NSE",
        "trade_date": date(2026, 5, 1),
        "trade_type": "buy",
        "quantity": 1.0,
        "price": 10.0,
        "note": None,
        "idempotency_key": "abcdefgh12",
    }
    return {**base, **kw}


def test_manual_trade_is_idempotent_and_uppercases():
    repo = FakeRepo()
    svc = LedgerService(repo)
    t = _trade()
    first = asyncio.run(svc.add_manual_trade(None, t))
    second = asyncio.run(svc.add_manual_trade(None, t))
    assert first["created"] is True and second["created"] is False
    assert next(iter(repo.fps.values()))["symbol"] == "INFY"
    assert "manual_abcdefgh12" in repo.fps


def test_recompute_failure_does_not_lose_write():
    async def boom(conn, cid):
        raise RuntimeError("worker down")

    res = asyncio.run(
        LedgerService(FakeRepo()).add_manual_trade(
            None, _trade(idempotency_key=None), boom
        )
    )
    assert res["created"] is True and res["recomputed"] is False


def test_side_filter_is_lowercased():
    repo = FakeRepo()
    asyncio.run(
        LedgerService(repo).list_trades_by_side(
            None, uuid.uuid4(), None, "BUY", None, None, 10, 0
        )
    )
    assert repo.calls[0][-1] == "buy"
