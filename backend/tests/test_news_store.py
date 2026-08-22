"""Store layer for the news pipeline: pdf_uploads, news_items, news_links (JsonStore).

Mirrors the async test pattern in test_ingestion_and_store.py.
"""
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.store import JsonStore


@pytest.mark.asyncio
async def test_pdf_upload_create_get_update_list():
    with tempfile.TemporaryDirectory() as d:
        store = JsonStore(d)
        await store.init()

        u = await store.create_pdf_upload(
            {
                "scope": "client", "owner_id": "c1", "file_name": "ET.pdf",
                "file_hash": "hash-1", "edition_date": "2026-08-18",
                "page_count": 16, "status": "PENDING",
            }
        )
        assert u["id"]
        assert (await store.get_pdf_upload(u["id"]))["status"] == "PENDING"

        updated = await store.update_pdf_upload(u["id"], {"status": "DONE", "items_created": 5})
        assert updated["status"] == "DONE"
        assert updated["items_created"] == 5

        assert await store.get_pdf_upload("does-not-exist") is None

        lst = await store.list_pdf_uploads("client", "c1")
        assert len(lst) == 1 and lst[0]["id"] == u["id"]
        assert await store.list_pdf_uploads("client", "someone-else") == []
        assert await store.list_pdf_uploads("manager", "c1") == []  # scope must match too


@pytest.mark.asyncio
async def test_pdf_upload_dedupe_by_hash_scoped():
    with tempfile.TemporaryDirectory() as d:
        store = JsonStore(d)
        await store.init()
        await store.create_pdf_upload(
            {"scope": "client", "owner_id": "c1", "file_hash": "same-hash", "status": "DONE"}
        )
        assert await store.pdf_upload_exists("client", "c1", "same-hash") is True
        assert await store.pdf_upload_exists("client", "c1", "other-hash") is False
        # same file hash under a different owner is NOT a dupe (each scope/owner re-processes)
        assert await store.pdf_upload_exists("client", "c2", "same-hash") is False


@pytest.mark.asyncio
async def test_news_items_query_by_symbol_sorted_newest_first():
    with tempfile.TemporaryDirectory() as d:
        store = JsonStore(d)
        await store.init()
        upload = await store.create_pdf_upload({"scope": "manager", "owner_id": "m1", "status": "DONE"})

        inserted = await store.insert_news_items(
            [
                {"pdf_upload_id": upload["id"], "page": 1, "title": "Older", "symbols": ["RELIANCE"],
                 "published_at": "2026-08-18T08:00:00"},
                {"pdf_upload_id": upload["id"], "page": 2, "title": "Newer", "symbols": ["RELIANCE", "TCS"],
                 "published_at": "2026-08-18T10:00:00"},
                {"pdf_upload_id": upload["id"], "page": 3, "title": "Unrelated", "symbols": ["INFY"],
                 "published_at": "2026-08-18T09:00:00"},
            ]
        )
        assert inserted == 3

        reliance_news = await store.news_for_symbol("reliance")  # lowercase input still matches
        assert [n["title"] for n in reliance_news] == ["Newer", "Older"]  # newest first

        multi = await store.news_for_symbols(["infy", "tcs"])
        assert {n["title"] for n in multi} == {"Newer", "Unrelated"}

        assert await store.news_for_symbol("NOBODY_HOLDS_THIS") == []


@pytest.mark.asyncio
async def test_news_for_symbol_respects_limit():
    with tempfile.TemporaryDirectory() as d:
        store = JsonStore(d)
        await store.init()
        upload = await store.create_pdf_upload({"scope": "manager", "owner_id": "m1", "status": "DONE"})
        await store.insert_news_items(
            [
                {"pdf_upload_id": upload["id"], "page": i, "title": f"Item {i}", "symbols": ["RELIANCE"],
                 "published_at": f"2026-08-18T{8+i:02d}:00:00"}
                for i in range(5)
            ]
        )
        assert len(await store.news_for_symbol("RELIANCE", limit=2)) == 2
        assert len(await store.news_for_symbol("RELIANCE", limit=100)) == 5


@pytest.mark.asyncio
async def test_cascade_delete_client_removes_uploads_items_links():
    with tempfile.TemporaryDirectory() as d:
        store = JsonStore(d)
        await store.init()
        await store.create_client({"id": "c1", "name": "Test Client", "portfolio_manager_id": "m1"})

        upload = await store.create_pdf_upload(
            {"scope": "client", "owner_id": "c1", "file_hash": "h1", "status": "DONE"}
        )
        await store.insert_news_items(
            [{"id": "item-1", "pdf_upload_id": upload["id"], "page": 1, "title": "X", "symbols": ["RELIANCE"]}]
        )
        await store.insert_news_links(
            [{"item_id": "item-1", "symbol": "RELIANCE", "confidence": 1.0, "match_method": "EXACT"}]
        )

        assert await store.delete_client("c1") is True

        assert await store.list_pdf_uploads("client", "c1") == []
        assert await store.news_for_symbol("RELIANCE") == []
        # the link row itself is gone too, not just unreachable via news_items
        assert store._db["news_links"] == []  # noqa: SLF001 (whitebox check on the JSON backend)


@pytest.mark.asyncio
async def test_cascade_delete_manager_removes_manager_scoped_uploads():
    with tempfile.TemporaryDirectory() as d:
        store = JsonStore(d)
        await store.init()
        await store.create_manager({"id": "m1", "name": "Test Manager"})

        upload = await store.create_pdf_upload(
            {"scope": "manager", "owner_id": "m1", "file_hash": "h1", "status": "DONE"}
        )
        await store.insert_news_items(
            [{"pdf_upload_id": upload["id"], "page": 1, "title": "Y", "symbols": ["TCS"]}]
        )

        assert await store.delete_manager("m1") is True
        assert await store.list_pdf_uploads("manager", "m1") == []
        assert await store.news_for_symbol("TCS") == []


@pytest.mark.asyncio
async def test_deleting_one_clients_uploads_does_not_touch_another_clients():
    with tempfile.TemporaryDirectory() as d:
        store = JsonStore(d)
        await store.init()
        await store.create_client({"id": "c1", "name": "Client One", "portfolio_manager_id": "m1"})
        await store.create_client({"id": "c2", "name": "Client Two", "portfolio_manager_id": "m1"})

        u1 = await store.create_pdf_upload({"scope": "client", "owner_id": "c1", "status": "DONE"})
        u2 = await store.create_pdf_upload({"scope": "client", "owner_id": "c2", "status": "DONE"})
        await store.insert_news_items(
            [{"pdf_upload_id": u1["id"], "page": 1, "title": "C1 story", "symbols": ["RELIANCE"]}]
        )
        await store.insert_news_items(
            [{"pdf_upload_id": u2["id"], "page": 1, "title": "C2 story", "symbols": ["RELIANCE"]}]
        )

        await store.delete_client("c1")

        remaining = await store.news_for_symbol("RELIANCE")
        assert len(remaining) == 1
        assert remaining[0]["title"] == "C2 story"
        assert len(await store.list_pdf_uploads("client", "c2")) == 1
