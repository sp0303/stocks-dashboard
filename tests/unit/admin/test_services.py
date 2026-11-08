"""Service rules with fake repositories."""

import json
import uuid
from datetime import date

import pytest
from pi_api.modules.admin.book_service import BookError, BookService
from pi_api.modules.admin.service import AdminError, AdminService

MGR = uuid.uuid4()


class _Conn:
    def transaction(self):
        class _T:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

        return _T()


class AdminRepoFake:
    def __init__(self, live=0, exists=True):
        self.live, self.exists, self.deleted = live, exists, []

    async def count_live_clients(self, conn, mid):
        return self.live

    async def soft_delete_manager(self, conn, mid):
        self.deleted.append(mid)
        return self.exists


@pytest.mark.asyncio
async def test_delete_manager_refused_with_clients_then_soft_deletes():
    with pytest.raises(AdminError) as e:
        await AdminService(repo=AdminRepoFake(live=2)).delete_manager(_Conn(), MGR)
    assert e.value.status == 409
    repo = AdminRepoFake()
    await AdminService(repo=repo).delete_manager(_Conn(), MGR)
    assert repo.deleted == [MGR]
    with pytest.raises(AdminError):
        await AdminService(repo=AdminRepoFake(exists=False)).delete_manager(
            _Conn(), MGR
        )


class BookRepoFake:
    async def roster(self, conn, mid):
        return [
            {
                "client_id": uuid.uuid4(),
                "name": "A",
                "client_code": "A1",
                "broker": "ZERODHA",
                "status": "ACTIVE",
                "as_of": date(2026, 11, 6),
                "trade_count": 3,
                "payload": json.dumps(
                    {
                        "market_value": 120.0,
                        "capital_deployed": 100.0,
                        "total_pnl": 20.0,
                    }
                ),
            },
            {
                "client_id": uuid.uuid4(),
                "name": "B",
                "client_code": None,
                "broker": None,
                "status": "ACTIVE",
                "as_of": None,
                "trade_count": 0,
                "payload": None,
            },
        ]

    async def positions(self, conn, mid):
        return [{"symbol": "AAA", "quantity": 1, "invested": 100, "price": 120}]

    async def trade_counts(self, conn, mid, since):
        return {"AAA": 3}


@pytest.mark.asyncio
async def test_summary_marks_uncomputed_clients_as_unknown():
    out = await BookService(repo=BookRepoFake()).summary(_Conn(), MGR)
    a, b = out["clients"]
    assert a["computed"] and a["market_value"] == 120.0
    assert not b["computed"] and b["market_value"] is None  # unknown, not 0
    assert out["totals"]["return_on_capital"] == pytest.approx(0.2)
    assert out["as_of"] == date(2026, 11, 6)
    assert out["insights"]["most_traded"] == {"symbol": "AAA", "value": 3}


class ClientsFake:
    def __init__(self, taken=False):
        self.taken = taken

    async def manager_exists(self, conn, mid):
        return True

    async def code_taken(self, conn, mid, code, exclude=None):
        return self.taken

    async def create_client(self, conn, mid, name, code, broker):
        return {"client_id": uuid.uuid4(), "manager_id": mid, "name": name}


@pytest.mark.asyncio
async def test_create_client_duplicate_code():
    with pytest.raises(BookError) as e:
        await BookService(clients=ClientsFake(taken=True)).create_client(
            _Conn(), MGR, "X", "C1", None
        )
    assert e.value.status == 409
    row = await BookService(clients=ClientsFake()).create_client(
        _Conn(), MGR, "X", "C1", None
    )
    assert row["manager_id"] == MGR
