"""Seed baseline managers + clients so the dashboard has something to show.

Idempotent: only seeds when there are no managers yet. No auth involved.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.store import BaseStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def seed_if_empty(store: BaseStore) -> None:
    if await store.list_managers():
        return

    m1 = await store.create_manager(
        {"name": "Ravi Kumar", "email": "ravi@firm.com", "firm": "Alpha Capital",
         "status": "ACTIVE", "created_at": _now()}
    )
    m2 = await store.create_manager(
        {"name": "Priya Nair", "email": "priya@firm.com", "firm": "Beta Wealth",
         "status": "ACTIVE", "created_at": _now()}
    )

    await store.create_client(
        {"name": "Laxman (Zerodha Main)", "portfolio_manager_id": m1["id"],
         "client_code": "QPJ806", "status": "ACTIVE",
         "onboarded_at": _now(), "created_at": _now()}
    )
    await store.create_client(
        {"name": "Lax Main Account", "portfolio_manager_id": m1["id"],
         "client_code": "AP8774", "status": "ACTIVE",
         "onboarded_at": _now(), "created_at": _now()}
    )
    await store.create_client(
        {"name": "Demo Client", "portfolio_manager_id": m2["id"],
         "client_code": None, "status": "ACTIVE",
         "onboarded_at": _now(), "created_at": _now()}
    )
